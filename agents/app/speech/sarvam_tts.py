"""
Phase 3D: Sarvam Bulbul v3 TTS Provider.

Verified API contract (sarvamai==0.1.34):
  - Connect: AsyncSarvamAI.text_to_speech_streaming.connect(model="bulbul:v3")
  - Configure: ws.configure(... output_audio_codec="linear16", speech_sample_rate=24000)
  - convert / flush / async for AudioOutput | ErrorResponse | EventResponse
  - AudioOutput.data.audio is base64; content_type is recorded from the live response

Channel layout is NOT assumed from Sarvam docs alone — see pcm_format.establish_channel_count.
"""

import asyncio
import logging
import time
from typing import AsyncIterator, Optional

from sarvamai import AsyncSarvamAI
from sarvamai.types import AudioOutput, ErrorResponse, EventResponse

from agents.app.speech.pcm_format import (
    InvalidPCMAudioError,
    VerifiedPCMChunk,
    decode_and_validate_sarvam_audio,
    establish_channel_count,
)

logger = logging.getLogger("roxstar.tts.sarvam")


class TTSCancelledError(Exception):
    """Raised when a TTS request is cancelled before completion."""


class TTSProviderError(Exception):
    """Raised on Sarvam ErrorResponse / invalid audio. Does not trigger LLM retry."""


def _sanitize_error_message(exc: BaseException) -> str:
    """Strip credential-bearing text from error strings before logging."""
    msg = str(exc)
    lowered = msg.lower()
    for marker in ("api-subscription-key", "api_subscription_key", "authorization"):
        if marker in lowered:
            return f"{type(exc).__name__}: [redacted provider error]"
    return f"{type(exc).__name__}: {msg[:300]}"


class SarvamTTSProvider:
    """Streaming Bulbul v3 TTS → validated linear16 VerifiedPCMChunk."""

    SAMPLE_RATE = 24000
    FRAME_DURATION_MS = 20
    SAMPLES_PER_FRAME = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 480

    def __init__(
        self,
        api_key: str,
        model: str = "bulbul:v3",
        language_code: str = "hi-IN",
        pace: float = 1.0,
        output_codec: str = "linear16",
        sample_rate: int = 24000,
        livekit_source_channels: int = 1,
    ):
        if not api_key or "placeholder" in api_key.lower():
            raise ValueError(
                "SARVAM_TTS_API_KEY is not configured. "
                "SarvamTTSProvider requires a valid API key. "
                "Set TTS_PROVIDER=mock for testing without credentials."
            )
        self._api_key = api_key
        self.model = model
        self.language_code = language_code
        self.pace = pace
        self.output_codec = output_codec
        self.sample_rate = sample_rate
        self.livekit_source_channels = livekit_source_channels
        self._cancel_events: dict[str, asyncio.Event] = {}
        self.last_stream_format: Optional[dict] = None

        logger.info(
            "SarvamTTSProvider initialized",
            extra={
                "model": self.model,
                "language_code": self.language_code,
                "pace": self.pace,
                "output_codec": self.output_codec,
                "sample_rate": self.sample_rate,
            },
        )

    def cancel_request(self, request_id: str) -> None:
        event = self._cancel_events.get(request_id)
        if event:
            event.set()
            logger.info(f"TTS cancellation signaled for request_id={request_id}")

    def _is_cancelled(self, request_id: str) -> bool:
        event = self._cancel_events.get(request_id)
        return event is not None and event.is_set()

    async def synthesize_stream(
        self,
        text_chunks: AsyncIterator[str],
        speaker: str,
        request_id: str,
        turn_id: str,
        agent_id: str,
    ) -> AsyncIterator[VerifiedPCMChunk]:
        """
        Stream validated PCM chunks incrementally (ordering preserved).

        Yields VerifiedPCMChunk after base64 decode + linear16 validation.
        """
        self._cancel_events[request_id] = asyncio.Event()

        t_start = time.perf_counter()
        t_first_audio: Optional[float] = None
        chunks_sent = 0
        audio_bytes_yielded = 0
        sequence = 0
        prior_channels: Optional[int] = None
        observed_content_types: set[str] = set()
        channel_evidence: Optional[str] = None

        logger.info(
            "tts.request.started",
            extra={
                "request_id": request_id,
                "turn_id": turn_id,
                "agent_id": agent_id,
                "speaker": speaker,
                "model": self.model,
                "language": self.language_code,
            },
        )

        try:
            client = AsyncSarvamAI(api_subscription_key=self._api_key)

            async with client.text_to_speech_streaming.connect(
                model=self.model,
                send_completion_event="true",
            ) as ws:
                await ws.configure(
                    target_language_code=self.language_code,
                    speaker=speaker,
                    pace=self.pace,
                    speech_sample_rate=self.sample_rate,
                    output_audio_codec=self.output_codec,
                    enable_preprocessing=True,
                )

                send_done = asyncio.Event()

                async def _send_text():
                    nonlocal chunks_sent
                    async for chunk in text_chunks:
                        if self._is_cancelled(request_id):
                            break
                        if chunk.strip():
                            await ws.convert(chunk)
                            chunks_sent += 1
                    await ws.flush()
                    send_done.set()

                send_task = asyncio.create_task(_send_text())

                try:
                    async for message in ws:
                        if self._is_cancelled(request_id):
                            send_task.cancel()
                            logger.info(
                                "tts.cancelled",
                                extra={
                                    "request_id": request_id,
                                    "turn_id": turn_id,
                                    "agent_id": agent_id,
                                    "speaker": speaker,
                                },
                            )
                            raise TTSCancelledError(
                                f"TTS request {request_id} cancelled during audio streaming"
                            )

                        if isinstance(message, ErrorResponse):
                            send_task.cancel()
                            err_msg = getattr(
                                getattr(message, "data", None), "message", None
                            ) or "Sarvam TTS ErrorResponse"
                            raise TTSProviderError(err_msg)

                        # Bulbul v3 sends EventResponse(event_type="final") when synthesis
                        # completes. Exit the receive loop — otherwise the socket idles until
                        # the server closes with "Websocket was left open without any messages".
                        if isinstance(message, EventResponse):
                            event_type = getattr(
                                getattr(message, "data", None), "event_type", None
                            )
                            if event_type == "final":
                                break
                            continue

                        if isinstance(message, AudioOutput):
                            content_type = getattr(message.data, "content_type", "") or ""
                            if content_type:
                                observed_content_types.add(content_type)

                            try:
                                verified = decode_and_validate_sarvam_audio(
                                    audio_b64=message.data.audio,
                                    content_type=content_type,
                                    configured_sample_rate=self.sample_rate,
                                    configured_codec=self.output_codec,
                                    livekit_source_channels=self.livekit_source_channels,
                                    prior_channels=prior_channels,
                                    sequence=sequence,
                                )
                            except InvalidPCMAudioError as exc:
                                send_task.cancel()
                                raise TTSProviderError(
                                    f"Invalid Sarvam audio payload: {exc}"
                                ) from exc

                            if channel_evidence is None:
                                _, channel_evidence = establish_channel_count(
                                    content_type=content_type,
                                    pcm_len=len(verified.pcm),
                                    configured_channels=None,
                                    livekit_source_channels=self.livekit_source_channels,
                                )
                            prior_channels = verified.channels

                            if t_first_audio is None:
                                t_first_audio = time.perf_counter()
                                ttfa_ms = round((t_first_audio - t_start) * 1000.0, 2)
                                logger.info(
                                    "tts.first_audio",
                                    extra={
                                        "request_id": request_id,
                                        "turn_id": turn_id,
                                        "agent_id": agent_id,
                                        "speaker": speaker,
                                        "model": self.model,
                                        "language": self.language_code,
                                        "ttfa_ms": ttfa_ms,
                                        "content_type": verified.content_type,
                                        "sample_rate": verified.sample_rate,
                                        "channels": verified.channels,
                                        "sample_width": verified.sample_width,
                                        "codec": verified.codec,
                                        "channel_evidence": channel_evidence,
                                    },
                                )

                            audio_bytes_yielded += len(verified.pcm)
                            sequence += 1
                            yield verified

                    await asyncio.wait_for(send_done.wait(), timeout=5.0)
                except (TTSCancelledError, TTSProviderError):
                    send_task.cancel()
                    raise
                except Exception:
                    send_task.cancel()
                    raise

                try:
                    await send_task
                except asyncio.CancelledError:
                    pass

            self.last_stream_format = {
                "codec": self.output_codec,
                "content_types": sorted(observed_content_types),
                "sample_rate": self.sample_rate,
                "channels": prior_channels,
                "sample_width": 2,
                "channel_evidence": channel_evidence,
                "audio_bytes": audio_bytes_yielded,
                "chunks": sequence,
            }

            ttfa_ms = (
                round((t_first_audio - t_start) * 1000.0, 2) if t_first_audio else None
            )
            total_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
            logger.info(
                "tts.completed",
                extra={
                    "request_id": request_id,
                    "turn_id": turn_id,
                    "agent_id": agent_id,
                    "speaker": speaker,
                    "model": self.model,
                    "language": self.language_code,
                    "ttfa_ms": ttfa_ms,
                    "total_ms": total_ms,
                    "audio_bytes": audio_bytes_yielded,
                    "text_chunks_sent": chunks_sent,
                    "content_types": sorted(observed_content_types),
                    "channels": prior_channels,
                    "channel_evidence": channel_evidence,
                },
            )

        except TTSCancelledError:
            raise
        except TTSProviderError as exc:
            logger.error(
                "tts.error",
                extra={
                    "request_id": request_id,
                    "turn_id": turn_id,
                    "agent_id": agent_id,
                    "speaker": speaker,
                    "model": self.model,
                    "error": str(exc)[:300],
                },
            )
            raise
        except Exception as exc:
            logger.error(
                "tts.error",
                extra={
                    "request_id": request_id,
                    "turn_id": turn_id,
                    "agent_id": agent_id,
                    "speaker": speaker,
                    "model": self.model,
                    "error": _sanitize_error_message(exc),
                },
            )
            raise
        finally:
            self._cancel_events.pop(request_id, None)


class MockTTSProvider:
    """
    Explicit mock for unit tests only. NEVER report as real TTS verification.
    Yields VerifiedPCMChunk silence frames (linear16 / 24kHz / 1ch) for wiring tests.
    """

    SAMPLE_RATE = 24000
    NUM_CHANNELS = 1
    FRAME_DURATION_MS = 20
    SAMPLES_PER_FRAME = 480
    SILENCE_FRAME = bytes(SAMPLES_PER_FRAME * 2)

    def __init__(self, **kwargs):
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._initialized = True
        self.last_stream_format: Optional[dict] = None
        logger.warning(
            "[MOCK TTS ACTIVE — TESTING ONLY] MockTTSProvider initialized. "
            "This provider MUST NOT be used in production or reported as real TTS verification."
        )

    def cancel_request(self, request_id: str) -> None:
        event = self._cancel_events.get(request_id)
        if event:
            event.set()

    def _is_cancelled(self, request_id: str) -> bool:
        event = self._cancel_events.get(request_id)
        return event is not None and event.is_set()

    async def synthesize_stream(
        self,
        text_chunks: AsyncIterator[str],
        speaker: str,
        request_id: str,
        turn_id: str,
        agent_id: str,
    ) -> AsyncIterator[VerifiedPCMChunk]:
        self._cancel_events[request_id] = asyncio.Event()
        try:
            text = ""
            async for chunk in text_chunks:
                if self._is_cancelled(request_id):
                    raise TTSCancelledError(f"Mock TTS cancelled: {request_id}")
                text += chunk

            if not text.strip():
                return

            num_frames = min(5, max(1, len(text) // 50))
            for seq in range(num_frames):
                if self._is_cancelled(request_id):
                    raise TTSCancelledError(f"Mock TTS cancelled: {request_id}")
                await asyncio.sleep(0)
                yield VerifiedPCMChunk(
                    pcm=self.SILENCE_FRAME,
                    content_type="audio/l16;rate=24000;channels=1",
                    sample_rate=self.SAMPLE_RATE,
                    channels=self.NUM_CHANNELS,
                    sample_width=2,
                    sequence=seq,
                    codec="linear16",
                )

            self.last_stream_format = {
                "codec": "linear16",
                "content_types": ["audio/l16;rate=24000;channels=1"],
                "sample_rate": self.SAMPLE_RATE,
                "channels": self.NUM_CHANNELS,
                "sample_width": 2,
                "channel_evidence": "mock content_type channels=1",
                "chunks": num_frames,
            }
        except TTSCancelledError:
            raise
        finally:
            self._cancel_events.pop(request_id, None)


def create_tts_provider(
    provider_type: Optional[str] = None,
    api_key: Optional[str] = None,
):
    """Factory: mock only when TTS_PROVIDER=mock is explicit."""
    try:
        from app.config import settings as backend_settings
        _settings = backend_settings
    except ImportError:
        try:
            from agents.app.config import agent_settings
            _settings = agent_settings
        except ImportError:
            _settings = None

    selected = (
        provider_type or getattr(_settings, "tts_provider", "sarvam") or "sarvam"
    ).lower().strip()

    if selected == "mock":
        return MockTTSProvider()

    # Explicit api_key="" must NOT fall back to settings (callers testing missing key).
    if api_key is None and _settings:
        effective_key = (
            getattr(_settings, "effective_tts_api_key", None)
            or getattr(_settings, "sarvam_tts_api_key", None)
            or getattr(_settings, "sarvam_api_key", None)
        )
    else:
        effective_key = api_key

    return SarvamTTSProvider(
        api_key=effective_key or "",
        model=getattr(_settings, "sarvam_tts_model", "bulbul:v3") if _settings else "bulbul:v3",
        language_code=getattr(_settings, "sarvam_tts_language", "hi-IN") if _settings else "hi-IN",
        pace=getattr(_settings, "sarvam_tts_pace", 1.0) if _settings else 1.0,
        output_codec=getattr(_settings, "sarvam_tts_output_codec", "linear16") if _settings else "linear16",
        sample_rate=getattr(_settings, "sarvam_tts_sample_rate", 24000) if _settings else 24000,
    )
