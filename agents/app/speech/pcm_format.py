"""
Phase 3D Step 3: PCM / linear16 audio format validation for Sarvam → LiveKit.

Does not invent format facts. Channel layout is established from:
1. Explicit MIME parameters on AudioOutput.content_type when present
2. Otherwise: evidence from configured request (linear16 @ speech_sample_rate)
   plus int16 little-endian byte layout, constrained to match the LiveKit
   AudioSource channel count used for publication.

Sarvam AudioOutput does not expose a dedicated channels field in sarvamai==0.1.34.
"""

from __future__ import annotations

import base64
import re
import struct
from dataclasses import dataclass
from typing import Optional


class InvalidPCMAudioError(ValueError):
    """Raised when decoded audio fails linear16 / layout validation."""


@dataclass(frozen=True)
class VerifiedPCMChunk:
    """One validated PCM chunk ready for LiveKit AudioFrame creation."""

    pcm: bytes
    content_type: str
    sample_rate: int
    channels: int
    sample_width: int  # bytes per sample (2 for int16)
    sequence: int
    codec: str = "linear16"

    @property
    def samples_per_channel(self) -> int:
        frame_bytes = self.channels * self.sample_width
        return len(self.pcm) // frame_bytes if frame_bytes else 0


_RATE_RE = re.compile(r"(?:rate|sampling[_-]?rate)=(\d+)", re.IGNORECASE)
_CH_RE = re.compile(r"channels?=(\d+)", re.IGNORECASE)


def decode_base64_audio(audio_b64: str) -> bytes:
    """Decode Sarvam AudioOutput.data.audio base64 payload to raw bytes."""
    if not isinstance(audio_b64, str) or not audio_b64.strip():
        raise InvalidPCMAudioError("Audio payload is empty or not a base64 string")
    try:
        raw = base64.b64decode(audio_b64, validate=False)
    except Exception as exc:
        raise InvalidPCMAudioError(f"Base64 decode failed: {exc}") from exc
    if not raw:
        raise InvalidPCMAudioError("Decoded audio is empty")
    return raw


def parse_content_type_audio_params(content_type: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    """
    Extract sample_rate / channels from MIME content_type when present.

    Examples observed/expected:
      - audio/l16;rate=24000;channels=1
      - audio/pcm
      - audio/wav
    Returns (sample_rate, channels); either may be None if absent.
    """
    if not content_type:
        return None, None
    rate_m = _RATE_RE.search(content_type)
    ch_m = _CH_RE.search(content_type)
    rate = int(rate_m.group(1)) if rate_m else None
    channels = int(ch_m.group(1)) if ch_m else None
    return rate, channels


def establish_channel_count(
    *,
    content_type: Optional[str],
    pcm_len: int,
    configured_channels: Optional[int],
    livekit_source_channels: int,
) -> tuple[int, str]:
    """
    Establish channel count with explicit evidence string.

    Priority:
    1. content_type channels=N
    2. configured_channels if provided by caller from a prior verified stream
    3. livekit_source_channels only when pcm_len is divisible by (channels * 2)
       AND content_type did not contradict — documented as constrained by the
       existing AudioSource (Step 2), not as an unverified Sarvam claim.
    """
    mime_rate, mime_ch = parse_content_type_audio_params(content_type)
    _ = mime_rate  # rate handled separately

    if mime_ch is not None:
        if mime_ch < 1:
            raise InvalidPCMAudioError(f"Invalid channels in content_type: {mime_ch}")
        frame = mime_ch * 2
        if pcm_len % frame != 0:
            raise InvalidPCMAudioError(
                f"PCM length {pcm_len} not divisible by channels*{2}={frame} "
                f"(content_type={content_type!r})"
            )
        return mime_ch, f"content_type channels={mime_ch}"

    if configured_channels is not None:
        frame = configured_channels * 2
        if pcm_len % frame != 0:
            raise InvalidPCMAudioError(
                f"PCM length {pcm_len} not divisible by configured channels*{2}={frame}"
            )
        return configured_channels, f"prior_verified_channels={configured_channels}"

    # No channel metadata from Sarvam AudioOutput in SDK types.
    # Constrain to LiveKit AudioSource channel count so frames are publishable.
    frame = livekit_source_channels * 2
    if livekit_source_channels < 1 or pcm_len % frame != 0:
        raise InvalidPCMAudioError(
            f"Cannot establish channel layout: content_type={content_type!r}, "
            f"pcm_len={pcm_len}, livekit_source_channels={livekit_source_channels}. "
            "Sarvam AudioOutput has no channels field (sarvamai==0.1.34)."
        )
    return (
        livekit_source_channels,
        (
            "no channels in AudioOutput; Sarvam SDK exposes content_type + base64 only; "
            f"PCM len divisible by int16*{livekit_source_channels}; "
            f"publishing constrained to LiveKit AudioSource channels={livekit_source_channels}"
        ),
    )


def validate_linear16_pcm(
    pcm: bytes,
    *,
    content_type: str,
    configured_sample_rate: int,
    configured_codec: str = "linear16",
    livekit_source_channels: int = 1,
    prior_channels: Optional[int] = None,
    sequence: int = 0,
) -> VerifiedPCMChunk:
    """
    Validate decoded bytes as little-endian int16 PCM suitable for LiveKit AudioFrame.

    - codec must be linear16 (configured; response content_type recorded)
    - byte length must support int16 samples
    - sample rate from content_type if present, else configured request rate
    - channels via establish_channel_count()
    """
    if configured_codec != "linear16":
        raise InvalidPCMAudioError(
            f"Only linear16 is supported for LiveKit PCM path, got {configured_codec!r}"
        )
    if not pcm:
        raise InvalidPCMAudioError("PCM bytes are empty")
    if len(pcm) % 2 != 0:
        raise InvalidPCMAudioError(
            f"linear16 PCM byte length must be even (int16), got {len(pcm)}"
        )

    mime_rate, _ = parse_content_type_audio_params(content_type)
    sample_rate = mime_rate if mime_rate is not None else configured_sample_rate
    if sample_rate != configured_sample_rate:
        raise InvalidPCMAudioError(
            f"Sample rate mismatch: content_type rate={mime_rate}, "
            f"configured={configured_sample_rate}"
        )

    channels, _evidence = establish_channel_count(
        content_type=content_type,
        pcm_len=len(pcm),
        configured_channels=prior_channels,
        livekit_source_channels=livekit_source_channels,
    )

    # Confirm unpackable as little-endian int16 (layout check; do not log samples)
    sample_count = len(pcm) // 2
    try:
        struct.unpack(f"<{sample_count}h", pcm)
    except struct.error as exc:
        raise InvalidPCMAudioError(f"PCM is not valid little-endian int16: {exc}") from exc

    frame = channels * 2
    if len(pcm) % frame != 0:
        raise InvalidPCMAudioError(
            f"PCM length {len(pcm)} not aligned to channels={channels} frames"
        )

    return VerifiedPCMChunk(
        pcm=pcm,
        content_type=content_type or "unknown",
        sample_rate=sample_rate,
        channels=channels,
        sample_width=2,
        sequence=sequence,
        codec="linear16",
    )


def decode_and_validate_sarvam_audio(
    *,
    audio_b64: str,
    content_type: str,
    configured_sample_rate: int = 24000,
    configured_codec: str = "linear16",
    livekit_source_channels: int = 1,
    prior_channels: Optional[int] = None,
    sequence: int = 0,
) -> VerifiedPCMChunk:
    """Base64-decode Sarvam audio then validate as linear16 PCM."""
    pcm = decode_base64_audio(audio_b64)
    return validate_linear16_pcm(
        pcm,
        content_type=content_type,
        configured_sample_rate=configured_sample_rate,
        configured_codec=configured_codec,
        livekit_source_channels=livekit_source_channels,
        prior_channels=prior_channels,
        sequence=sequence,
    )
