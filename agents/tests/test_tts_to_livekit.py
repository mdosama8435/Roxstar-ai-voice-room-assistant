"""
Phase 3D Step 3: Focused tests for Sarvam → PCM validation → LiveKit publish wiring.

Uses mock providers / synthetic PCM for unit coverage.
Does NOT claim real Sarvam or human-hearing verification.
"""

from __future__ import annotations

import base64
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.app.livekit.audio_publisher import LiveKitAudioPublisher, _extract_pcm_bytes
from agents.app.speech.pcm_format import (
    InvalidPCMAudioError,
    VerifiedPCMChunk,
    decode_and_validate_sarvam_audio,
    decode_base64_audio,
    establish_channel_count,
    parse_content_type_audio_params,
    validate_linear16_pcm,
)
from agents.app.speech.sarvam_tts import (
    MockTTSProvider,
    TTSProviderError,
)
from agents.app.speech.tts_livekit_bridge import synthesize_and_publish
from agents.app.agents.personas import DOST_PERSONA, SATHI_PERSONA


def _pcm_silence(samples: int = 480, channels: int = 1) -> bytes:
    return bytes(samples * channels * 2)


class TestBase64AndLinear16Validation:
    def test_decode_base64_roundtrip(self):
        original = struct.pack("<480h", *([0] * 480))
        encoded = base64.b64encode(original).decode("ascii")
        assert decode_base64_audio(encoded) == original

    def test_decode_rejects_empty(self):
        with pytest.raises(InvalidPCMAudioError):
            decode_base64_audio("")

    def test_validate_linear16_even_length_and_int16(self):
        pcm = _pcm_silence(480)
        verified = validate_linear16_pcm(
            pcm,
            content_type="audio/l16;rate=24000;channels=1",
            configured_sample_rate=24000,
        )
        assert verified.sample_rate == 24000
        assert verified.channels == 1
        assert verified.sample_width == 2
        assert verified.codec == "linear16"
        assert verified.samples_per_channel == 480

    def test_validate_rejects_odd_byte_length(self):
        with pytest.raises(InvalidPCMAudioError, match="even"):
            validate_linear16_pcm(
                b"\x00\x01\x02",
                content_type="audio/pcm",
                configured_sample_rate=24000,
            )

    def test_validate_rejects_sample_rate_mismatch_in_content_type(self):
        pcm = _pcm_silence(480)
        with pytest.raises(InvalidPCMAudioError, match="Sample rate mismatch"):
            validate_linear16_pcm(
                pcm,
                content_type="audio/l16;rate=16000;channels=1",
                configured_sample_rate=24000,
            )

    def test_content_type_channel_param_wins(self):
        # 480 samples * 2 ch * 2 bytes
        pcm = _pcm_silence(480, channels=2)
        ch, evidence = establish_channel_count(
            content_type="audio/l16;rate=24000;channels=2",
            pcm_len=len(pcm),
            configured_channels=None,
            livekit_source_channels=1,
        )
        assert ch == 2
        assert "content_type" in evidence

    def test_no_channel_metadata_constrained_to_livekit_source(self):
        pcm = _pcm_silence(480, channels=1)
        ch, evidence = establish_channel_count(
            content_type="audio/pcm",
            pcm_len=len(pcm),
            configured_channels=None,
            livekit_source_channels=1,
        )
        assert ch == 1
        assert "no channels in AudioOutput" in evidence
        assert "LiveKit AudioSource" in evidence

    def test_decode_and_validate_sarvam_audio(self):
        pcm = _pcm_silence(240)
        b64 = base64.b64encode(pcm).decode("ascii")
        verified = decode_and_validate_sarvam_audio(
            audio_b64=b64,
            content_type="audio/l16;rate=24000;channels=1",
            configured_sample_rate=24000,
            sequence=3,
        )
        assert verified.sequence == 3
        assert verified.pcm == pcm


class TestAudioFrameConversion:
    def test_extract_pcm_from_verified_chunk(self):
        chunk = VerifiedPCMChunk(
            pcm=_pcm_silence(480),
            content_type="audio/l16;rate=24000;channels=1",
            sample_rate=24000,
            channels=1,
            sample_width=2,
            sequence=0,
        )
        assert len(_extract_pcm_bytes(chunk)) == 960

    def test_extract_rejects_channel_mismatch(self):
        chunk = VerifiedPCMChunk(
            pcm=_pcm_silence(480, channels=2),
            content_type="audio/l16;rate=24000;channels=2",
            sample_rate=24000,
            channels=2,
            sample_width=2,
            sequence=0,
        )
        with pytest.raises(ValueError, match="channels"):
            _extract_pcm_bytes(chunk)

    @pytest.mark.asyncio
    async def test_publisher_builds_audio_frame_from_verified_chunks(self):
        publisher = LiveKitAudioPublisher(agent_id="dost")
        captured = []

        class _Src:
            async def capture_frame(self, frame):
                captured.append(frame)

        publisher._audio_source = _Src()
        publisher._published = True

        async def stream():
            yield VerifiedPCMChunk(
                pcm=_pcm_silence(480),
                content_type="audio/l16;rate=24000;channels=1",
                sample_rate=24000,
                channels=1,
                sample_width=2,
                sequence=0,
            )
            yield VerifiedPCMChunk(
                pcm=_pcm_silence(480),
                content_type="audio/l16;rate=24000;channels=1",
                sample_rate=24000,
                channels=1,
                sample_width=2,
                sequence=1,
            )

        with patch("livekit.rtc.AudioFrame") as frame_cls:
            frame_cls.side_effect = lambda **kwargs: MagicMock(**kwargs)
            await publisher.publish_pcm_stream(stream(), request_id="r1", turn_id="t1")

        assert frame_cls.call_count == 2
        first_kwargs = frame_cls.call_args_list[0].kwargs
        assert first_kwargs["sample_rate"] == 24000
        assert first_kwargs["num_channels"] == 1
        assert first_kwargs["samples_per_channel"] == 480
        assert len(captured) == 2


class TestChunkOrderingAndErrors:
    @pytest.mark.asyncio
    async def test_mock_stream_preserves_sequence_order(self):
        mock = MockTTSProvider()

        async def text_gen():
            yield "A" * 200

        seqs = []
        async for chunk in mock.synthesize_stream(
            text_chunks=text_gen(),
            speaker="shubh",
            request_id="ord-1",
            turn_id="t",
            agent_id="dost",
        ):
            seqs.append(chunk.sequence)
        assert seqs == list(range(len(seqs)))

    @pytest.mark.asyncio
    async def test_bridge_reports_provider_error_without_raising_llm_retry(self):
        class FailingProvider:
            last_stream_format = None

            async def synthesize_stream(self, **kwargs):
                raise TTSProviderError("speaker rejected")
                yield  # pragma: no cover — async generator

        publisher = LiveKitAudioPublisher(agent_id="sathi")
        publisher._audio_source = MagicMock()
        publisher._published = True

        async def consume_publish(pcm_stream, request_id, turn_id):
            async for _ in pcm_stream:
                pass

        publisher.publish_pcm_stream = consume_publish

        result = await synthesize_and_publish(
            provider=FailingProvider(),
            publisher=publisher,
            text="Namaste",
            speaker="priya",
            agent_id="sathi",
        )
        assert result.success is False
        assert "speaker rejected" in (result.error or "")

    @pytest.mark.asyncio
    async def test_bridge_publishes_mock_audio_through_publisher(self):
        mock = MockTTSProvider()
        publisher = LiveKitAudioPublisher(agent_id="dost")
        publisher._audio_source = MagicMock()
        publisher._published = True

        published = []

        async def fake_publish(pcm_stream, request_id, turn_id):
            async for chunk in pcm_stream:
                published.append(chunk)

        publisher.publish_pcm_stream = fake_publish

        result = await synthesize_and_publish(
            provider=mock,
            publisher=publisher,
            text="Haan yaar, test message for audio path.",
            speaker="shubh",
            agent_id="dost",
        )
        assert result.success is True
        assert result.chunks_published == len(published) > 0
        assert [c.sequence for c in published] == list(range(len(published)))
        assert result.codec == "linear16"
        assert result.sample_rate == 24000


class TestSpeakerConfiguration:
    def test_dost_speaker_is_shubh(self):
        assert DOST_PERSONA.voice_id == "shubh"

    def test_sathi_speaker_is_priya_live_verified_v3(self):
        # Live Sarvam bulbul:v3 rejects anushka; priya confirmed.
        assert SATHI_PERSONA.voice_id == "priya"

    def test_parse_content_type_params(self):
        rate, ch = parse_content_type_audio_params("audio/l16;rate=24000;channels=1")
        assert rate == 24000
        assert ch == 1
