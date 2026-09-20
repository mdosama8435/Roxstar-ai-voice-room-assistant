"""
Phase 3D Step 3: Bridge validated Sarvam TTS chunks → LiveKitAudioPublisher.

agents/ media plane only. Does not call LLM, does not retry LLM on TTS failure.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import AsyncIterator, Optional, Union

from agents.app.livekit.audio_publisher import LiveKitAudioPublisher
from agents.app.speech.pcm_format import VerifiedPCMChunk
from agents.app.speech.sarvam_tts import (
    MockTTSProvider,
    SarvamTTSProvider,
    TTSCancelledError,
    TTSProviderError,
)

logger = logging.getLogger("roxstar.agents.tts_livekit_bridge")

TTSProvider = Union[SarvamTTSProvider, MockTTSProvider]


@dataclass
class TTSPublishResult:
    request_id: str
    turn_id: str
    agent_id: str
    speaker: str
    chunks_published: int
    bytes_published: int
    content_types: list[str]
    sample_rate: Optional[int]
    channels: Optional[int]
    sample_width: Optional[int]
    codec: str
    channel_evidence: Optional[str]
    success: bool
    error: Optional[str] = None


async def _text_as_stream(text: str) -> AsyncIterator[str]:
    yield text


async def synthesize_and_publish(
    *,
    provider: TTSProvider,
    publisher: LiveKitAudioPublisher,
    text: str,
    speaker: str,
    agent_id: str,
    turn_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> TTSPublishResult:
    """
    Validated AI text → Sarvam (or mock) → LiveKitAudioPublisher.publish_pcm_stream.

    Streams incrementally; preserves chunk order via publisher queue.
    On TTSProviderError: logs and returns failure — does NOT trigger LLM.
    """
    req_id = request_id or f"tts-{uuid.uuid4().hex[:12]}"
    turn = turn_id or f"turn-{uuid.uuid4().hex[:12]}"
    text = (text or "").strip()

    if not text:
        return TTSPublishResult(
            request_id=req_id,
            turn_id=turn,
            agent_id=agent_id,
            speaker=speaker,
            chunks_published=0,
            bytes_published=0,
            content_types=[],
            sample_rate=None,
            channels=None,
            sample_width=None,
            codec="linear16",
            channel_evidence=None,
            success=False,
            error="empty_text",
        )

    if not publisher._audio_source or not publisher._published:
        return TTSPublishResult(
            request_id=req_id,
            turn_id=turn,
            agent_id=agent_id,
            speaker=speaker,
            chunks_published=0,
            bytes_published=0,
            content_types=[],
            sample_rate=None,
            channels=None,
            sample_width=None,
            codec="linear16",
            channel_evidence=None,
            success=False,
            error="publisher_not_ready",
        )

    chunks = 0
    total_bytes = 0
    sequences: list[int] = []

    async def _ordered_stream() -> AsyncIterator[VerifiedPCMChunk]:
        nonlocal chunks, total_bytes
        async for verified in provider.synthesize_stream(
            text_chunks=_text_as_stream(text),
            speaker=speaker,
            request_id=req_id,
            turn_id=turn,
            agent_id=agent_id,
        ):
            sequences.append(verified.sequence)
            chunks += 1
            total_bytes += len(verified.pcm)
            yield verified

    try:
        await publisher.publish_pcm_stream(
            pcm_stream=_ordered_stream(),
            request_id=req_id,
            turn_id=turn,
        )
    except TTSCancelledError as exc:
        fmt = getattr(provider, "last_stream_format", None) or {}
        return TTSPublishResult(
            request_id=req_id,
            turn_id=turn,
            agent_id=agent_id,
            speaker=speaker,
            chunks_published=chunks,
            bytes_published=total_bytes,
            content_types=list(fmt.get("content_types") or []),
            sample_rate=fmt.get("sample_rate"),
            channels=fmt.get("channels"),
            sample_width=fmt.get("sample_width"),
            codec=fmt.get("codec") or "linear16",
            channel_evidence=fmt.get("channel_evidence"),
            success=False,
            error=f"cancelled:{exc}",
        )
    except TTSProviderError as exc:
        # TTS failure must not escalate into a new LLM generation.
        logger.error(
            "tts.publish.failed",
            extra={
                "request_id": req_id,
                "turn_id": turn,
                "agent_id": agent_id,
                "speaker": speaker,
                "error": str(exc)[:300],
            },
        )
        fmt = getattr(provider, "last_stream_format", None) or {}
        return TTSPublishResult(
            request_id=req_id,
            turn_id=turn,
            agent_id=agent_id,
            speaker=speaker,
            chunks_published=chunks,
            bytes_published=total_bytes,
            content_types=list(fmt.get("content_types") or []),
            sample_rate=fmt.get("sample_rate"),
            channels=fmt.get("channels"),
            sample_width=fmt.get("sample_width"),
            codec=fmt.get("codec") or "linear16",
            channel_evidence=fmt.get("channel_evidence"),
            success=False,
            error=str(exc)[:300],
        )
    except Exception as exc:
        logger.error(
            "tts.publish.failed",
            extra={
                "request_id": req_id,
                "turn_id": turn,
                "agent_id": agent_id,
                "speaker": speaker,
                "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            },
        )
        return TTSPublishResult(
            request_id=req_id,
            turn_id=turn,
            agent_id=agent_id,
            speaker=speaker,
            chunks_published=chunks,
            bytes_published=total_bytes,
            content_types=[],
            sample_rate=None,
            channels=None,
            sample_width=None,
            codec="linear16",
            channel_evidence=None,
            success=False,
            error=f"{type(exc).__name__}: {str(exc)[:300]}",
        )

    # Ordering check: sequences must be strictly increasing by 1 from 0
    if sequences and sequences != list(range(len(sequences))):
        logger.error(
            "tts.publish.order_violation",
            extra={"request_id": req_id, "sequences_head": sequences[:20]},
        )
        return TTSPublishResult(
            request_id=req_id,
            turn_id=turn,
            agent_id=agent_id,
            speaker=speaker,
            chunks_published=chunks,
            bytes_published=total_bytes,
            content_types=[],
            sample_rate=None,
            channels=None,
            sample_width=None,
            codec="linear16",
            channel_evidence=None,
            success=False,
            error="chunk_order_violation",
        )

    fmt = getattr(provider, "last_stream_format", None) or {}
    return TTSPublishResult(
        request_id=req_id,
        turn_id=turn,
        agent_id=agent_id,
        speaker=speaker,
        chunks_published=chunks,
        bytes_published=total_bytes,
        content_types=list(fmt.get("content_types") or []),
        sample_rate=fmt.get("sample_rate"),
        channels=fmt.get("channels"),
        sample_width=fmt.get("sample_width"),
        codec=fmt.get("codec") or "linear16",
        channel_evidence=fmt.get("channel_evidence"),
        success=chunks > 0 and total_bytes > 0,
        error=None if chunks > 0 else "no_audio_chunks",
    )
