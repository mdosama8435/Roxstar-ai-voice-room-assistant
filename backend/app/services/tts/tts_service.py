"""
Phase 3D Step 4: TTS Service — Orchestrates TTS after canonical LLM text.

Pipeline:
  TTSRequest (canonical validated AI text)
      ↓
  TextChunker
      ↓
  SarvamTTSProvider / MockTTSProvider
      ↓
  LiveKitAudioPublisher for the SELECTED agent only
      ↓
  audio.published

Guarantees:
- TTS failure does NOT trigger LLM retry
- Cancellation clears provider + audio queue; late chunks discarded by publisher
- Only the selected agent_id publisher is used (no dual-AI overlap)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, Optional

from app.schemas.tts import (
    TTSErrorCategory,
    TTSMetrics,
    TTSRequest,
    TTSStatus,
)

logger = logging.getLogger("roxstar.tts.service")

EventListener = Callable[[str, Dict[str, Any]], None]


class TTSService:
    """
    Coordinates TTS synthesis from canonical AI text to LiveKit audio.

    Publishers are keyed by agent_id ('dost' | 'sathi'). Only the selected
    agent's publisher receives audio — non-selected agents stay silent.
    """

    def __init__(
        self,
        tts_provider=None,
        audio_publisher=None,
        publishers: Optional[Dict[str, Any]] = None,
        min_chunk_chars: int = 40,
        max_chunk_chars: int = 250,
        event_listener: Optional[EventListener] = None,
    ):
        self.tts_provider = tts_provider
        self.audio_publisher = audio_publisher  # optional default / single-publisher mode
        self._publishers: Dict[str, Any] = dict(publishers or {})
        self.min_chunk_chars = min_chunk_chars
        self.max_chunk_chars = max_chunk_chars
        self._event_listener = event_listener

        self._active_requests: dict[str, TTSMetrics] = {}
        self._completed_requests: dict[str, TTSMetrics] = {}
        self._cancel_reasons: dict[str, str] = {}
        # request_id → room_id for DataChannel observability broadcasts
        self._rooms_by_request: dict[str, str] = {}

    def set_event_listener(self, listener: Optional[EventListener]) -> None:
        self._event_listener = listener

    def set_publisher(self, agent_id: str, publisher) -> None:
        """Register LiveKitAudioPublisher for one AI participant."""
        self._publishers[agent_id.lower()] = publisher

    def get_publisher(self, agent_id: str):
        key = (agent_id or "").lower()
        return self._publishers.get(key) or self.audio_publisher

    def _emit(self, event_type: str, **payload: Any) -> None:
        # Never log secrets or raw audio
        safe = {k: v for k, v in payload.items() if k not in ("audio", "pcm", "api_key", "text")}
        if "text_length" not in safe and "text" in payload and isinstance(payload.get("text"), str):
            safe["text_length"] = len(payload["text"])
        logger.info(event_type, extra=safe)
        if self._event_listener:
            try:
                self._event_listener(event_type, safe)
            except Exception as exc:
                logger.warning("TTS event listener error: %s", exc)

    async def synthesize_and_publish(self, request: TTSRequest) -> Optional[TTSMetrics]:
        """
        Run TTS for one canonical response.

        Returns TTSMetrics on success, None on failure/cancellation.
        Does NOT trigger LLM regeneration.
        """
        from app.services.tts.text_chunker import chunk_text_stream
        from agents.app.speech.sarvam_tts import TTSCancelledError, TTSProviderError
        from agents.app.speech.pcm_format import VerifiedPCMChunk

        if not self.tts_provider:
            self._emit(
                "tts.failed",
                request_id=request.request_id,
                turn_id=request.turn_id,
                agent_id=request.agent_id,
                room_id=request.room_id,
                error_category=TTSErrorCategory.UNKNOWN.value,
                error="tts_provider_missing",
            )
            return None

        publisher = self.get_publisher(request.agent_id)
        metrics = TTSMetrics(
            request_id=request.request_id,
            turn_id=request.turn_id,
            agent_id=request.agent_id,
            speaker=request.speaker,
            model=request.model,
            language_code=request.language_code,
            tts_request_start=time.perf_counter(),
            status=TTSStatus.STREAMING,
        )
        self._active_requests[request.request_id] = metrics
        self._cancel_reasons.pop(request.request_id, None)
        self._rooms_by_request[request.request_id] = request.room_id

        self._emit(
            "tts.started",
            request_id=request.request_id,
            turn_id=request.turn_id,
            agent_id=request.agent_id,
            room_id=request.room_id,
            speaker=request.speaker,
            model=request.model,
            language=request.language_code,
            text_length=len(request.text or ""),
            publisher_bound=publisher is not None,
        )

        chunks_out = 0
        bytes_out = 0

        try:
            async def _single_text_stream():
                yield request.text

            chunked_text = chunk_text_stream(
                _single_text_stream(),
                min_chunk_chars=self.min_chunk_chars,
                max_chunk_chars=self.max_chunk_chars,
            )

            pcm_stream = self.tts_provider.synthesize_stream(
                text_chunks=chunked_text,
                speaker=request.speaker,
                request_id=request.request_id,
                turn_id=request.turn_id,
                agent_id=request.agent_id,
            )

            async def _instrumented_stream():
                nonlocal chunks_out, bytes_out
                async for item in pcm_stream:
                    # Abort if cancelled mid-stream (do not resume)
                    if request.request_id in self._cancel_reasons:
                        raise TTSCancelledError(
                            f"TTS {request.request_id} cancelled: "
                            f"{self._cancel_reasons[request.request_id]}"
                        )

                    pcm = item.pcm if isinstance(item, VerifiedPCMChunk) else item
                    if not pcm:
                        continue

                    if metrics.tts_first_audio_at is None:
                        metrics.tts_first_audio_at = time.perf_counter()
                        self._emit(
                            "tts.first_audio",
                            request_id=request.request_id,
                            turn_id=request.turn_id,
                            agent_id=request.agent_id,
                            room_id=request.room_id,
                            speaker=request.speaker,
                            ttfa_ms=metrics.time_to_first_audio_ms,
                            sample_rate=getattr(item, "sample_rate", None),
                            channels=getattr(item, "channels", None),
                            content_type=getattr(item, "content_type", None),
                        )

                    chunks_out += 1
                    bytes_out += len(pcm)
                    metrics.total_chunks = chunks_out
                    metrics.total_bytes = bytes_out
                    yield item

            if publisher is not None:
                await publisher.publish_pcm_stream(
                    pcm_stream=_instrumented_stream(),
                    request_id=request.request_id,
                    turn_id=request.turn_id,
                )
                self._emit(
                    "audio.published",
                    request_id=request.request_id,
                    turn_id=request.turn_id,
                    agent_id=request.agent_id,
                    room_id=request.room_id,
                    chunks=chunks_out,
                    bytes=bytes_out,
                )
            else:
                # Publisher missing = no LiveKit audio path. Do NOT pretend success
                # and do NOT burn Sarvam quota by synthesizing into the void.
                metrics.status = TTSStatus.FAILED
                self._emit(
                    "tts.failed",
                    request_id=request.request_id,
                    turn_id=request.turn_id,
                    agent_id=request.agent_id,
                    room_id=request.room_id,
                    error_category=TTSErrorCategory.UNKNOWN.value,
                    error="publisher_not_bound",
                )
                return None

            if request.request_id in self._cancel_reasons:
                metrics.status = TTSStatus.CANCELLED
                self._emit(
                    "tts.cancelled",
                    request_id=request.request_id,
                    turn_id=request.turn_id,
                    agent_id=request.agent_id,
                    room_id=request.room_id,
                    reason=self._cancel_reasons.get(request.request_id),
                    chunks=chunks_out,
                )
                return None

            metrics.tts_completion_at = time.perf_counter()
            metrics.status = TTSStatus.COMPLETED
            self._emit(
                "tts.completed",
                request_id=request.request_id,
                turn_id=request.turn_id,
                agent_id=request.agent_id,
                room_id=request.room_id,
                speaker=request.speaker,
                ttfa_ms=metrics.time_to_first_audio_ms,
                total_ms=metrics.tts_total_ms,
                chunks=chunks_out,
                bytes=bytes_out,
            )
            return metrics

        except asyncio.CancelledError:
            metrics.status = TTSStatus.CANCELLED
            self._emit(
                "tts.cancelled",
                request_id=request.request_id,
                turn_id=request.turn_id,
                agent_id=request.agent_id,
                room_id=request.room_id,
                reason="asyncio.CancelledError",
                chunks=chunks_out,
            )
            self._emit(
                "audio.cancelled",
                request_id=request.request_id,
                turn_id=request.turn_id,
                agent_id=request.agent_id,
                room_id=request.room_id,
                reason="asyncio.CancelledError",
            )
            raise

        except TTSCancelledError as exc:
            metrics.status = TTSStatus.CANCELLED
            self._emit(
                "tts.cancelled",
                request_id=request.request_id,
                turn_id=request.turn_id,
                agent_id=request.agent_id,
                room_id=request.room_id,
                reason=str(exc)[:200],
                chunks=chunks_out,
            )
            self._emit(
                "audio.cancelled",
                request_id=request.request_id,
                turn_id=request.turn_id,
                agent_id=request.agent_id,
                room_id=request.room_id,
                reason=str(exc)[:200],
            )
            return None

        except Exception as exc:
            error_name = type(exc).__name__
            metrics.status = TTSStatus.FAILED
            category = TTSErrorCategory.UNKNOWN
            msg = str(exc)
            if isinstance(exc, TTSProviderError):
                category = TTSErrorCategory.UNKNOWN
            if "401" in msg or "credentials" in msg.lower() or "unauthorized" in msg.lower():
                category = TTSErrorCategory.AUTHENTICATION
            elif "429" in msg or "rate" in msg.lower() or "quota" in msg.lower():
                category = TTSErrorCategory.RATE_LIMIT
            elif "timeout" in msg.lower():
                category = TTSErrorCategory.TIMEOUT
            elif "websocket" in msg.lower() or "connection" in msg.lower():
                category = TTSErrorCategory.WEBSOCKET_DISCONNECT
            elif "cancelled" in msg.lower():
                category = TTSErrorCategory.CANCELLED
                metrics.status = TTSStatus.CANCELLED

            self._emit(
                "tts.failed",
                request_id=request.request_id,
                turn_id=request.turn_id,
                agent_id=request.agent_id,
                room_id=request.room_id,
                speaker=request.speaker,
                model=request.model,
                error_category=category.value,
                error_type=error_name,
            )
            return None

        finally:
            self._active_requests.pop(request.request_id, None)
            self._completed_requests[request.request_id] = metrics
            self._cancel_reasons.pop(request.request_id, None)
            self._rooms_by_request.pop(request.request_id, None)

    async def cancel(self, request_id: str, reason: str = "barge_in") -> None:
        """Cancel active TTS: stop provider, clear audio queue, discard late chunks."""
        self._cancel_reasons[request_id] = reason
        metrics = self._active_requests.get(request_id)
        if metrics:
            metrics.status = TTSStatus.CANCELLED
            agent_id = metrics.agent_id
        else:
            agent_id = "unknown"

        if self.tts_provider and hasattr(self.tts_provider, "cancel_request"):
            try:
                self.tts_provider.cancel_request(request_id)
            except Exception as exc:
                logger.warning("TTS provider cancel error: %s", type(exc).__name__)

        # Clear selected publisher queue; also clear default if present
        publishers = set()
        if metrics:
            pub = self.get_publisher(metrics.agent_id)
            if pub is not None:
                publishers.add(pub)
        for pub in self._publishers.values():
            publishers.add(pub)
        if self.audio_publisher is not None:
            publishers.add(self.audio_publisher)

        for pub in publishers:
            if hasattr(pub, "cancel_current"):
                try:
                    await pub.cancel_current(request_id)
                except Exception as exc:
                    logger.warning("Audio publisher cancel error: %s", type(exc).__name__)

        room_id = self._rooms_by_request.get(request_id)
        self._emit(
            "tts.cancelled",
            request_id=request_id,
            agent_id=agent_id,
            room_id=room_id,
            reason=reason,
        )
        self._emit(
            "audio.cancelled",
            request_id=request_id,
            agent_id=agent_id,
            room_id=room_id,
            reason=reason,
        )

    def get_metrics(self, request_id: str) -> Optional[TTSMetrics]:
        return (
            self._active_requests.get(request_id)
            or self._completed_requests.get(request_id)
        )

    def get_active_request_ids(self) -> list:
        return list(self._active_requests.keys())

    def is_request_active(self, request_id: str) -> bool:
        return request_id in self._active_requests
