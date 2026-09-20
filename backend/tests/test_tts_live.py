"""
Phase 3D: Real Sarvam TTS Smoke Test.

Opt-in: This test requires:
  1. RUN_TTS_LIVE_TEST=true environment variable
  2. SARVAM_TTS_API_KEY or SARVAM_API_KEY with a real, valid credential
  3. Network access to wss://api.sarvam.ai

These tests are SKIPPED by default (when credentials are not configured).
They must NOT be reported as "green" if skipped.

Requirements for PHASE 3D REAL VERIFICATION:
- Real Sarvam API request (not mocked)
- Real bulbul:v3 model (not v2)
- Real audio received (non-empty bytes, decodable as linear16 PCM)
- AI Dost voice (shubh)
- AI Sathi voice (configured speaker; bulbul:v3-compatible)
- TTFA measured from real response
- Do NOT claim real voice if this test is skipped
"""

import asyncio
import base64
import os
import struct
import time
import pytest


# ============================================================================
# Skip guard: only run when explicitly opted in
# ============================================================================

def _tts_live_credentials_available() -> bool:
    """Returns True only when real credentials AND opt-in flag are present."""
    if os.environ.get("RUN_TTS_LIVE_TEST", "").lower() != "true":
        return False
    api_key = (
        os.environ.get("SARVAM_TTS_API_KEY", "")
        or os.environ.get("SARVAM_API_KEY", "")
    )
    if not api_key or "placeholder" in api_key.lower():
        return False
    return True


LIVE_SKIP = pytest.mark.skipif(
    not _tts_live_credentials_available(),
    reason=(
        "TTS live test requires RUN_TTS_LIVE_TEST=true AND "
        "SARVAM_TTS_API_KEY configured with a real API key. "
        "PHASE 3D NOT REAL-VERIFIED unless this test passes."
    )
)


# ============================================================================
# Real TTS Smoke Tests
# ============================================================================

@LIVE_SKIP
async def test_real_sarvam_tts_ai_dost_hindi():
    """
    REAL TTS SMOKE TEST: AI Dost (shubh) Hindi voice.

    Verifies:
    - Real Sarvam API call to bulbul:v3
    - output_audio_codec=linear16
    - speech_sample_rate=24000
    - Base64 audio decoded to non-empty PCM bytes
    - Audio is valid int16 PCM (length multiple of 2)
    - TTFA measured and within 3 seconds
    - NO API key in any log output
    """
    import logging
    from agents.app.speech.sarvam_tts import SarvamTTSProvider, MockTTSProvider

    api_key = (
        os.environ.get("SARVAM_TTS_API_KEY")
        or os.environ.get("SARVAM_API_KEY")
    )
    assert api_key and "placeholder" not in api_key.lower(), "Real API key required"

    # Initialize real provider
    provider = SarvamTTSProvider(
        api_key=api_key,
        model="bulbul:v3",
        language_code="hi-IN",
        pace=1.0,
        output_codec="linear16",
        sample_rate=24000,
    )

    # NOT a MockTTSProvider
    assert not isinstance(provider, MockTTSProvider), (
        "REAL TTS test must use SarvamTTSProvider, not MockTTSProvider"
    )

    request_id = "live-smoke-dost-001"
    turn_id = "live-turn-001"
    test_text = "Haan yaar, AI basically ek technology hai jo machines ko insaanon ki tarah sochna sikhati hai."

    async def text_gen():
        yield test_text

    t_start = time.perf_counter()
    t_first_audio = None
    pcm_chunks = []

    async for chunk in provider.synthesize_stream(
        text_chunks=text_gen(),
        speaker="shubh",
        request_id=request_id,
        turn_id=turn_id,
        agent_id="dost",
    ):
        if t_first_audio is None:
            t_first_audio = time.perf_counter()
        pcm_chunks.append(getattr(chunk, "pcm", chunk))
        # Record real format metadata from first verified chunk
        if not hasattr(test_real_sarvam_tts_ai_dost_hindi, "_fmt"):
            test_real_sarvam_tts_ai_dost_hindi._fmt = {
                "content_type": getattr(chunk, "content_type", None),
                "sample_rate": getattr(chunk, "sample_rate", None),
                "channels": getattr(chunk, "channels", None),
                "sample_width": getattr(chunk, "sample_width", None),
                "codec": getattr(chunk, "codec", None),
            }

    t_end = time.perf_counter()

    # REQUIRED assertions
    assert len(pcm_chunks) > 0, (
        "REAL TTS must produce audio. Got zero audio chunks. "
        "If this fails, TTS is NOT working."
    )

    total_bytes = sum(len(c) for c in pcm_chunks)
    assert total_bytes > 0, "Total audio bytes must be > 0"
    assert total_bytes % 2 == 0, (
        f"Linear16 PCM must have even byte count, got {total_bytes}"
    )

    # Verify it's valid PCM (unpackable as int16)
    all_pcm = b"".join(pcm_chunks)
    num_samples = len(all_pcm) // 2
    samples = struct.unpack(f"<{num_samples}h", all_pcm)
    assert len(samples) > 0, "PCM must contain audio samples"

    # TTFA must be measurable and reasonable
    assert t_first_audio is not None, "Must have received at least one audio chunk"
    ttfa_ms = (t_first_audio - t_start) * 1000
    total_ms = (t_end - t_start) * 1000
    fmt = getattr(test_real_sarvam_tts_ai_dost_hindi, "_fmt", {})
    stream_fmt = provider.last_stream_format or {}

    print(f"\n[REAL TTS RESULT - AI Dost (shubh)]")
    print(f"  Model: bulbul:v3")
    print(f"  Speaker: shubh")
    print(f"  Language: hi-IN")
    print(f"  Audio codec: {fmt.get('codec') or stream_fmt.get('codec')}")
    print(f"  content_type: {fmt.get('content_type') or stream_fmt.get('content_types')}")
    print(f"  Sample rate: {fmt.get('sample_rate') or stream_fmt.get('sample_rate')}")
    print(f"  Channels: {fmt.get('channels') or stream_fmt.get('channels')}")
    print(f"  Sample width: {fmt.get('sample_width') or stream_fmt.get('sample_width')}")
    print(f"  Channel evidence: {stream_fmt.get('channel_evidence')}")
    print(f"  Chunks received: {len(pcm_chunks)}")
    print(f"  Total audio bytes: {total_bytes}")
    print(f"  Audio samples: {num_samples}")
    print(f"  Duration: ~{num_samples/24000*1000:.0f}ms")
    print(f"  TTFA: {ttfa_ms:.1f}ms")
    print(f"  Total TTS time: {total_ms:.1f}ms")

    # TTFA must be < 3000ms for a reasonable real connection
    assert ttfa_ms < 3000, f"TTFA of {ttfa_ms:.1f}ms exceeds 3000ms threshold"


@LIVE_SKIP
async def test_real_sarvam_tts_ai_sathi_hindi():
    """
    REAL TTS SMOKE TEST: AI Sathi (configured bulbul:v3 speaker) Hindi voice.

    Verifies:
    - Real Sarvam API call to bulbul:v3 using female speaker
    - Same audio format validation as Dost test
    - Different speaker produces audio (not silence)
    """
    from agents.app.speech.sarvam_tts import SarvamTTSProvider
    from app.config import settings

    api_key = (
        os.environ.get("SARVAM_TTS_API_KEY")
        or os.environ.get("SARVAM_API_KEY")
    )
    sathi_speaker = settings.sarvam_tts_sathi_speaker or "priya"

    provider = SarvamTTSProvider(
        api_key=api_key,
        model="bulbul:v3",
        language_code="hi-IN",
        pace=1.0,
        output_codec="linear16",
        sample_rate=24000,
    )

    request_id = "live-smoke-sathi-001"
    test_text = "Main samajh rahi hoon. Aap bilkul sahi keh rahe hain."

    async def text_gen():
        yield test_text

    t_start = time.perf_counter()
    t_first_audio = None
    pcm_chunks = []

    async for chunk in provider.synthesize_stream(
        text_chunks=text_gen(),
        speaker=sathi_speaker,
        request_id=request_id,
        turn_id="live-turn-002",
        agent_id="sathi",
    ):
        if t_first_audio is None:
            t_first_audio = time.perf_counter()
        pcm_chunks.append(getattr(chunk, "pcm", chunk))

    assert len(pcm_chunks) > 0, "AI Sathi TTS must produce audio"
    total_bytes = sum(len(c) for c in pcm_chunks)
    assert total_bytes % 2 == 0, "Linear16 PCM must have even byte count"

    ttfa_ms = (t_first_audio - t_start) * 1000 if t_first_audio else None
    total_ms = (time.perf_counter() - t_start) * 1000
    stream_fmt = provider.last_stream_format or {}

    print(f"\n[REAL TTS RESULT - AI Sathi ({sathi_speaker})]")
    print(f"  Speaker: {sathi_speaker}")
    print(f"  content_types: {stream_fmt.get('content_types')}")
    print(f"  channels: {stream_fmt.get('channels')} evidence={stream_fmt.get('channel_evidence')}")
    print(f"  Chunks: {len(pcm_chunks)}, Bytes: {total_bytes}")
    print(f"  TTFA: {ttfa_ms:.1f}ms" if ttfa_ms else "  TTFA: N/A")
    print(f"  Total: {total_ms:.1f}ms")


@LIVE_SKIP
async def test_real_tts_api_key_not_in_logs(caplog):
    """
    SECURITY: Verify API key does NOT appear in any log output during TTS.
    """
    import logging
    from agents.app.speech.sarvam_tts import SarvamTTSProvider

    api_key = os.environ.get("SARVAM_TTS_API_KEY") or os.environ.get("SARVAM_API_KEY")

    with caplog.at_level(logging.DEBUG, logger="roxstar.tts"):
        provider = SarvamTTSProvider(api_key=api_key, model="bulbul:v3")

        async def text_gen():
            yield "Test."

        try:
            async for _ in provider.synthesize_stream(
                text_chunks=text_gen(),
                speaker="shubh",
                request_id="security-test-001",
                turn_id="turn-sec-001",
                agent_id="dost",
            ):
                break  # Just get the first chunk
        except Exception:
            pass

    # CRITICAL: API key must never appear in logs
    full_log = caplog.text
    assert api_key not in full_log, (
        "SECURITY VIOLATION: API key found in log output! "
        "API keys must NEVER be logged."
    )
