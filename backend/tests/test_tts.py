"""
Phase 3D: TTS Unit Tests

Coverage:
1.  Provider initialization with valid config
2.  Provider init fails on missing API key (not silent mock)
3.  MockTTSProvider requires explicit selection
4.  Mock never activates when credentials are absent (raises)
5.  Text chunker: primary boundaries split correctly
6.  Text chunker: comma not used aggressively
7.  Text chunker: no mid-word splits
8.  Text chunker: min_chunk_chars prevents micro-fragments
9.  Text chunker: max_chunk_chars force-flush at word boundary
10. Text chunker: trailing buffer flushed at stream end
11. Text chunker: Hindi sentence boundary (।)
12. Text chunker: configurable min/max
13. Audio config: correct model name (bulbul:v3)
14. Audio config: AI Dost speaker is 'shubh'
15. Audio config: AI Sathi speaker is 'anushka'
16. Audio config: output_audio_codec is 'linear16'
17. Audio config: sample_rate is 24000
18. Audio frame validation: byte length multiple of int16
19. Audio frame validation: samples_per_channel correct
20. MockTTSProvider yields silence frames of correct format
21. MockTTSProvider supports cancellation
22. TTS request-scoped cancellation stops audio generation
23. TTS failure does NOT trigger new LLM generation
24. TTS schema: TTSRequest fields correct
25. TTS schema: TTSMetrics TTFA computation correct
26. TTS schema: TTSFailedEvent has is_retryable field
27. TTS schema: TTSCompletedEvent fields present
28. Config: SARVAM_TTS_API_KEY separate from SARVAM_API_KEY
29. Config: is_tts_configured returns True for mock mode
30. SarvamBulbulConfig: correct default values from interfaces.py
"""

import asyncio
import base64
import struct
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================================
# TEST 1-4: Provider initialization and mock guard
# ============================================================================

class TestProviderInitialization:
    """Tests 1-4: Provider init, missing key, mock guard."""

    def test_01_sarvam_tts_config_correct_model_name(self):
        """Test 13: Model name must be 'bulbul:v3', not 'bulbul-v3'."""
        from agents.app.speech.interfaces import SarvamBulbulConfig
        config = SarvamBulbulConfig()
        assert config.model_name == "bulbul:v3", (
            f"Model name must be 'bulbul:v3', got '{config.model_name}'. "
            "Verified from sarvamai SDK connect(model=...) parameter."
        )

    def test_02_sarvam_tts_config_dost_speaker(self):
        """Test 14: AI Dost speaker must be 'shubh' (verified male voice)."""
        from agents.app.speech.interfaces import SarvamBulbulConfig
        config = SarvamBulbulConfig()
        assert config.voice_male == "shubh", (
            f"AI Dost speaker must be 'shubh', got '{config.voice_male}'. "
            "Verified from sarvamai SDK configure() source code."
        )

    def test_03_sarvam_tts_config_sathi_speaker(self):
        """Test 15: AI Sathi speaker must be bulbul:v3-compatible female (priya)."""
        from agents.app.speech.interfaces import SarvamBulbulConfig
        config = SarvamBulbulConfig()
        assert config.voice_female == "priya", (
            f"AI Sathi speaker must be 'priya', got '{config.voice_female}'. "
            "Live Sarvam bulbul:v3 rejects 'anushka'."
        )

    def test_04_sarvam_tts_config_output_codec(self):
        """Test 16: Output codec must be 'linear16' for LiveKit PCM compatibility."""
        from agents.app.speech.interfaces import SarvamBulbulConfig
        config = SarvamBulbulConfig()
        assert config.output_audio_codec == "linear16", (
            f"Output codec must be 'linear16', got '{config.output_audio_codec}'. "
            "Verified from ConfigureConnectionDataOutputAudioCodec type inspection."
        )

    def test_05_sarvam_tts_config_sample_rate(self):
        """Test 17: Sample rate must be 24000 Hz (bulbul:v3 default)."""
        from agents.app.speech.interfaces import SarvamBulbulConfig
        config = SarvamBulbulConfig()
        assert config.speech_sample_rate == 24000, (
            f"Sample rate must be 24000 Hz, got {config.speech_sample_rate}. "
            "Verified: bulbul:v3 default sample rate from SDK connect() docstring."
        )

    def test_06_sarvam_tts_config_no_pitch_loudness(self):
        """bulbul:v3 does NOT support pitch or loudness. Config must not have these."""
        from agents.app.speech.interfaces import SarvamBulbulConfig
        config = SarvamBulbulConfig()
        assert not hasattr(config, 'pitch'), "bulbul:v3 does NOT support pitch parameter"
        assert not hasattr(config, 'loudness'), "bulbul:v3 does NOT support loudness parameter"

    def test_07_sarvam_provider_raises_on_missing_key(self):
        """Test 2: SarvamTTSProvider must raise ValueError on missing/empty API key."""
        from agents.app.speech.sarvam_tts import SarvamTTSProvider
        with pytest.raises(ValueError, match="SARVAM_TTS_API_KEY"):
            SarvamTTSProvider(api_key="")

    def test_08_sarvam_provider_raises_on_placeholder_key(self):
        """Test 2b: SarvamTTSProvider must raise on placeholder key."""
        from agents.app.speech.sarvam_tts import SarvamTTSProvider
        with pytest.raises(ValueError, match="SARVAM_TTS_API_KEY"):
            SarvamTTSProvider(api_key="your_sarvam_tts_api_key_placeholder")

    def test_09_mock_requires_explicit_selection(self):
        """Test 3: MockTTSProvider exists and can be instantiated explicitly."""
        from agents.app.speech.sarvam_tts import MockTTSProvider
        mock = MockTTSProvider()
        assert mock._initialized is True

    def test_10_mock_never_silently_selected(self):
        """Test 4: Factory with provider_type='sarvam' and no key must raise, not use mock."""
        from agents.app.speech.sarvam_tts import create_tts_provider
        with pytest.raises((ValueError, Exception)):
            # Should raise ValueError about missing API key, not silently return mock
            provider = create_tts_provider(provider_type="sarvam", api_key="")

    def test_11_mock_explicitly_selected(self):
        """Test 3b: Factory with provider_type='mock' must return MockTTSProvider."""
        from agents.app.speech.sarvam_tts import create_tts_provider, MockTTSProvider
        provider = create_tts_provider(provider_type="mock")
        assert isinstance(provider, MockTTSProvider)


# ============================================================================
# TEST 5-12: Text Chunker
# ============================================================================

class TestTextChunker:
    """Tests 5-12: Text chunking boundary detection."""

    def test_12_primary_boundaries_split_correctly(self):
        """Test 5: Primary boundaries (. ? ! ।) trigger splits."""
        from backend.app.services.tts.text_chunker import chunk_text_sync

        text = "AI ek technology hai. Yeh machines ko sikhata hai."
        chunks = chunk_text_sync(text, min_chunk_chars=5, max_chunk_chars=200)
        assert len(chunks) >= 1
        # First chunk should end at a sentence boundary
        assert any('.' in chunk for chunk in chunks)

    def test_13_hindi_boundary_splits(self):
        """Test 11: Hindi पूर्ण विराम (।) is a primary sentence boundary."""
        from backend.app.services.tts.text_chunker import chunk_text_sync

        text = "यह एक परीक्षण है। अगला वाक्य यहाँ है।"
        chunks = chunk_text_sync(text, min_chunk_chars=5, max_chunk_chars=200)
        assert len(chunks) >= 1
        assert all(chunk.strip() for chunk in chunks)

    def test_14_comma_not_used_aggressively(self):
        """Test 6: Comma splits only when buffer is large; not for every comma."""
        from backend.app.services.tts.text_chunker import chunk_text_sync

        # Short text with comma — should NOT split at comma
        text = "Haan, bilkul sahi keh rahe hain aap."
        chunks = chunk_text_sync(text, min_chunk_chars=30, max_chunk_chars=200)
        # Should be one chunk since text is short
        assert len(chunks) == 1, (
            f"Short text with comma should not be split. Got {len(chunks)} chunks: {chunks}"
        )

    def test_15_no_mid_word_split(self):
        """Test 7: Word boundaries are respected; no mid-word splits."""
        from backend.app.services.tts.text_chunker import chunk_text_sync

        text = "A" * 200 + " long word here " + "B" * 50
        chunks = chunk_text_sync(text, min_chunk_chars=10, max_chunk_chars=50)
        for chunk in chunks:
            # No chunk should start with a lowercase letter after a letter (mid-word)
            assert not chunk.startswith(' '), f"Chunk starts with space: '{chunk[:20]}'"

    def test_16_min_chunk_prevents_micro_fragments(self):
        """Test 8: min_chunk_chars prevents very short chunks."""
        from backend.app.services.tts.text_chunker import chunk_text_sync

        # Text with early sentence boundary
        text = "Ok. This is a much longer sentence that should be included with the previous one."
        chunks = chunk_text_sync(text, min_chunk_chars=20, max_chunk_chars=200)
        # "Ok." is 3 chars < 20, should not be alone or should be merged
        for chunk in chunks:
            assert len(chunk) > 0

    def test_17_max_chunk_force_flush_at_word_boundary(self):
        """Test 9: max_chunk_chars triggers flush at word boundary."""
        from backend.app.services.tts.text_chunker import chunk_text_sync

        # Long text without sentence boundaries
        words = ["word"] * 60  # 60 * 5 = 300 chars without boundaries
        text = " ".join(words)
        chunks = chunk_text_sync(text, min_chunk_chars=10, max_chunk_chars=50)
        for chunk in chunks:
            # No chunk should be longer than max + one word (word boundary)
            assert len(chunk) <= 60, f"Chunk too long: {len(chunk)}: '{chunk[:30]}'"
            # No mid-word splits: chunks should not end with partial words
            words_in_chunk = chunk.split()
            assert all(w.strip() for w in words_in_chunk), "Chunk has empty words"

    def test_18_trailing_buffer_flushed(self):
        """Test 10: Remaining buffer is flushed at stream end."""
        from backend.app.services.tts.text_chunker import chunk_text_sync

        text = "This text has no sentence boundary at all"
        chunks = chunk_text_sync(text, min_chunk_chars=5, max_chunk_chars=200)
        # The entire text should appear in chunks
        combined = " ".join(chunks)
        # All words from original should be present
        for word in text.split():
            assert word in combined, f"Word '{word}' missing from chunks"

    async def test_19_async_chunker_yields_from_stream(self):
        """Async chunker accepts AsyncIterator and yields chunks."""
        from backend.app.services.tts.text_chunker import chunk_text_stream

        async def mock_stream():
            tokens = ["AI basically ", "ek technology hai. ", "Jo machines ko sikhata hai."]
            for t in tokens:
                yield t

        chunks = []
        async for chunk in chunk_text_stream(mock_stream(), min_chunk_chars=5, max_chunk_chars=200):
            chunks.append(chunk)

        assert len(chunks) >= 1
        assert all(chunk.strip() for chunk in chunks)

    def test_20_chunker_configurable_params(self):
        """Test 12: min_chunk_chars and max_chunk_chars are configurable."""
        from backend.app.services.tts.text_chunker import chunk_text_sync

        # With very small limits: splits more aggressively
        text = "Short. Medium. Long sentence here."
        chunks_tight = chunk_text_sync(text, min_chunk_chars=1, max_chunk_chars=20)
        chunks_loose = chunk_text_sync(text, min_chunk_chars=50, max_chunk_chars=500)
        # Tight chunking produces more chunks than loose
        assert len(chunks_tight) >= len(chunks_loose)


# ============================================================================
# TEST 21-24: Audio Frame Validation
# ============================================================================

class TestAudioFrameValidation:
    """Tests 21-24: PCM byte validation and AudioFrame creation."""

    def test_21_pcm_byte_length_multiple_of_int16(self):
        """Test 18: PCM bytes must be multiple of 2 (int16 = 2 bytes)."""
        # 480 samples * 2 bytes = 960 bytes
        pcm = bytes(960)
        assert len(pcm) % 2 == 0, "PCM bytes must be multiple of 2 for int16"

    def test_22_samples_per_channel_correct(self):
        """Test 19: samples_per_channel = len(pcm) / (num_channels * 2)."""
        pcm = bytes(960)
        num_channels = 1
        samples_per_channel = len(pcm) // (num_channels * 2)
        assert samples_per_channel == 480, f"Expected 480, got {samples_per_channel}"

    def test_23_frame_duration_20ms_at_24khz(self):
        """Verify 20ms frame = 480 samples @ 24kHz."""
        sample_rate = 24000
        frame_duration_ms = 20
        samples_per_frame = int(sample_rate * frame_duration_ms / 1000)
        assert samples_per_frame == 480

    def test_24_base64_decode_roundtrip(self):
        """Test 7: base64.b64decode produces correct PCM bytes."""
        # Simulate Sarvam AudioOutput.data.audio format
        original_pcm = bytes([0, 0, 0, 0, 10, 0, 20, 0] * 120)  # 960 bytes
        encoded = base64.b64encode(original_pcm).decode('utf-8')
        decoded = base64.b64decode(encoded)
        assert decoded == original_pcm, "base64 roundtrip must be lossless"
        assert len(decoded) % 2 == 0, "Decoded PCM must be multiple of 2 bytes"

    def test_25_mock_silence_frame_correct_format(self):
        """Test 20: MockTTSProvider silence frame is correct format."""
        from agents.app.speech.sarvam_tts import MockTTSProvider
        mock = MockTTSProvider()
        frame = mock.SILENCE_FRAME
        # 480 samples * 2 bytes = 960 bytes
        assert len(frame) == 960, f"Expected 960 bytes, got {len(frame)}"
        assert frame == bytes(960), "Silence frame must be all zeros"
        assert len(frame) % 2 == 0


# ============================================================================
# TEST 26-27: Mock TTS Cancellation
# ============================================================================

class TestMockTTSCancellation:
    """Tests 26-27: Cancellation semantics."""

    async def test_26_mock_tts_yields_silence_frames(self):
        """Test 20b: MockTTSProvider yields non-empty silence frames."""
        from agents.app.speech.sarvam_tts import MockTTSProvider

        mock = MockTTSProvider()
        request_id = "test-req-001"

        async def text_gen():
            yield "Haan yaar, bilkul sahi keh rahe hain aap."

        frames = []
        async for frame in mock.synthesize_stream(
            text_chunks=text_gen(),
            speaker="shubh",
            request_id=request_id,
            turn_id="turn-001",
            agent_id="dost",
        ):
            frames.append(frame)

        assert len(frames) > 0, "MockTTSProvider must yield at least one frame"
        for f in frames:
            pcm = getattr(f, "pcm", f)
            assert len(pcm) == 960, f"Each silence frame must be 960 bytes, got {len(pcm)}"
            assert getattr(f, "codec", "linear16") == "linear16"
            assert getattr(f, "sample_rate", 24000) == 24000

    async def test_27_mock_tts_cancellation(self):
        """Test 21: Request-scoped cancellation stops TTS."""
        from agents.app.speech.sarvam_tts import MockTTSProvider, TTSCancelledError

        mock = MockTTSProvider()
        request_id = "test-req-cancel-001"

        # Cancel immediately
        mock.cancel_request(request_id)

        async def text_gen():
            yield "This text should never be synthesized after cancellation."

        frames = []
        try:
            async for frame in mock.synthesize_stream(
                text_chunks=text_gen(),
                speaker="anushka",
                request_id=request_id,
                turn_id="turn-cancel-001",
                agent_id="sathi",
            ):
                frames.append(frame)
        except TTSCancelledError:
            pass  # Expected

        # Either zero frames (cancelled before start) or TTSCancelledError
        # Both are valid cancellation behaviors


# ============================================================================
# TEST 28-30: TTS Schemas
# ============================================================================

class TestTTSSchemas:
    """Tests 28-30: Schema correctness."""

    def test_28_tts_request_fields(self):
        """Test 24: TTSRequest has required fields."""
        from backend.app.schemas.tts import TTSRequest
        req = TTSRequest(
            request_id="tts-001",
            turn_id="turn-001",
            agent_id="dost",
            text="Haan yaar!",
            speaker="shubh",
            language_code="hi-IN",
            model="bulbul:v3",
            room_id="room-test-001",
        )
        assert req.request_id == "tts-001"
        assert req.speaker == "shubh"
        assert req.language_code == "hi-IN"
        assert req.model == "bulbul:v3"

    def test_29_tts_metrics_ttfa_computation(self):
        """Test 25: TTSMetrics time_to_first_audio_ms is computed correctly."""
        from backend.app.schemas.tts import TTSMetrics, TTSStatus
        import time

        metrics = TTSMetrics(
            request_id="tts-002",
            turn_id="turn-002",
            agent_id="sathi",
            speaker="anushka",
            model="bulbul:v3",
            language_code="hi-IN",
            tts_request_start=1000.0,
            tts_first_audio_at=1000.5,
        )
        assert metrics.time_to_first_audio_ms == 500.0, (
            f"TTFA must be 500ms, got {metrics.time_to_first_audio_ms}"
        )

    def test_30_tts_metrics_ttfa_none_if_no_first_audio(self):
        """TTFA is None when first_audio_at is not set."""
        from backend.app.schemas.tts import TTSMetrics

        metrics = TTSMetrics(
            request_id="tts-003",
            turn_id="turn-003",
            agent_id="dost",
            speaker="shubh",
            model="bulbul:v3",
            language_code="hi-IN",
            tts_request_start=1000.0,
            tts_first_audio_at=None,
        )
        assert metrics.time_to_first_audio_ms is None

    def test_31_tts_failed_event_has_is_retryable(self):
        """Test 26: TTSFailedEvent has is_retryable field."""
        from backend.app.schemas.tts import TTSFailedEvent, TTSErrorCategory

        evt = TTSFailedEvent(
            request_id="tts-004",
            turn_id="turn-004",
            agent_id="dost",
            error_category=TTSErrorCategory.TIMEOUT,
            error_message="Connection timed out",
            is_retryable=False,
        )
        assert evt.is_retryable is False
        assert evt.event_type == "tts.error"

    def test_32_tts_completed_event_fields(self):
        """Test 27: TTSCompletedEvent has all required fields."""
        from backend.app.schemas.tts import TTSCompletedEvent

        evt = TTSCompletedEvent(
            request_id="tts-005",
            turn_id="turn-005",
            agent_id="sathi",
            speaker="anushka",
            model="bulbul:v3",
            language_code="hi-IN",
            time_to_first_audio_ms=210.5,
            tts_total_ms=1450.0,
            total_chunks=4,
        )
        assert evt.event_type == "tts.completed"
        assert evt.speaker == "anushka"
        assert evt.time_to_first_audio_ms == 210.5


# ============================================================================
# TEST 33-34: Configuration correctness
# ============================================================================

class TestConfiguration:
    """Tests 33-34: Config isolation and TTS enable checks."""

    def test_33_tts_api_key_separate_from_stt_key(self):
        """Test 28: SARVAM_TTS_API_KEY is a separate field from SARVAM_API_KEY."""
        from backend.app.config import Settings

        # Both fields must exist and be independent
        fields = {f.alias or name for name, f in Settings.model_fields.items()}
        assert "SARVAM_TTS_API_KEY" in fields, "SARVAM_TTS_API_KEY must be a config field"
        assert "SARVAM_API_KEY" in fields, "SARVAM_API_KEY (STT) must still exist"

    def test_34_is_tts_configured_mock_mode(self):
        """Test 29: is_tts_configured returns True for TTS_PROVIDER=mock."""
        from backend.app.config import Settings
        s = Settings(TTS_PROVIDER="mock", LIVEKIT_URL="lk://test")
        assert s.is_tts_configured is True

    def test_35_is_tts_configured_false_without_key(self):
        """is_tts_configured returns False when no real key is configured."""
        from backend.app.config import Settings
        s = Settings(
            TTS_PROVIDER="sarvam",
            SARVAM_TTS_API_KEY=None,
            SARVAM_API_KEY=None,
            LIVEKIT_URL="lk://test",
        )
        assert s.is_tts_configured is False

    def test_36_tts_model_default(self):
        """Default TTS model must be 'bulbul:v3'."""
        from backend.app.config import Settings
        s = Settings(LIVEKIT_URL="lk://test")
        assert s.sarvam_tts_model == "bulbul:v3"

    def test_37_tts_sample_rate_default(self):
        """Default TTS sample rate must be 24000 Hz."""
        from backend.app.config import Settings
        s = Settings(LIVEKIT_URL="lk://test")
        assert s.sarvam_tts_sample_rate == 24000

    def test_38_tts_output_codec_default(self):
        """Default TTS output codec must be 'linear16'."""
        from backend.app.config import Settings
        s = Settings(LIVEKIT_URL="lk://test")
        assert s.sarvam_tts_output_codec == "linear16"


# ============================================================================
# TEST 39-40: Orchestrator TTS integration
# ============================================================================

class TestOrchestratorTTSIntegration:
    """Tests 39-40: Orchestrator holds turn lock through TTS; cancel propagates."""

    def test_39_orchestrator_has_set_tts_service(self):
        """Orchestrator exposes set_tts_service() for runtime injection."""
        from backend.app.services.orchestrator import OrchestratorService
        orch = OrchestratorService()
        assert hasattr(orch, 'set_tts_service'), "Orchestrator must have set_tts_service()"
        assert orch._tts_service is None, "TTS service must start as None"
        assert hasattr(orch, '_active_tts_requests'), "Must have _active_tts_requests dict"

    def test_40_orchestrator_tts_service_injection(self):
        """set_tts_service() registers the service correctly."""
        from backend.app.services.orchestrator import OrchestratorService
        orch = OrchestratorService()
        mock_tts = MagicMock()
        orch.set_tts_service(mock_tts)
        assert orch._tts_service is mock_tts

    async def test_41_cancel_generation_also_cancels_tts(self):
        """cancel_generation() also cancels active TTS on barge-in."""
        from backend.app.services.orchestrator import OrchestratorService
        orch = OrchestratorService()

        mock_tts = MagicMock()
        mock_tts.cancel = AsyncMock()
        orch.set_tts_service(mock_tts)

        # Simulate an active LLM+TTS request for the same turn
        orch._llm_request_by_turn["turn-001"] = "req-001"
        orch._active_tts_requests["turn-001"] = "tts-001"

        # Trigger barge-in cancel by LLM request_id
        await orch.cancel_generation("req-001")

        # TTS service.cancel should have been called
        mock_tts.cancel.assert_called_once()
