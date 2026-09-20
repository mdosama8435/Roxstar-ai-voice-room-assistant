"""
Comprehensive unit test suite for Phase 3C.1: Gemini Primary + NVIDIA NIM Controlled Failover.
Covers all 27 deterministic requirements from Section 19 using mocked providers.
"""

import asyncio
from datetime import datetime, timezone
from typing import AsyncIterator, List, Optional
import pytest

from app.config import Settings, settings
from app.schemas.contracts import BotType, ConversationTurn, OrchestrationDecision, ResponseEligibility, TriggerType, TurnState
from app.schemas.llm import LLMRequest, LLMResponse, LLMStreamChunk
from app.services.conversation_context import RoomContextSnapshot, SpeakerProfile
from app.services.llm.base import LLMProvider
from app.services.llm.errors import ErrorCategory, ProviderError
from app.services.llm.factory import create_concrete_provider, get_llm_provider
from app.services.llm.gemini_provider import GeminiLLMProvider
from app.services.llm.manager import LLMProviderManager
from app.services.llm.mock_provider import MockLLMProvider
from app.services.llm.nvidia_provider import NVIDIAProvider
from app.services.orchestrator import OrchestratorService
from app.services.turn_lock import turn_lock_manager


# ==============================================================================
# TEST FIXTURES & DETERMINISTIC MOCK PROVIDERS
# ==============================================================================

class DeterministicTestProvider(LLMProvider):
    """
    Instrumented mock provider for controlled testing of failover, latency, and errors.
    """

    def __init__(
        self,
        name: str = "mock_provider",
        response_text: str = "Test response",
        error_to_raise: Optional[Exception] = None,
        fail_after_n_chunks: int = 0,
        delay_seconds: float = 0.0,
    ) -> None:
        self.name = name
        self.response_text = response_text
        self.error_to_raise = error_to_raise
        self.fail_after_n_chunks = fail_after_n_chunks
        self.delay_seconds = delay_seconds
        self.call_count = 0
        self.stream_call_count = 0
        self.received_requests: List[LLMRequest] = []
        self.cancelled_request_ids: List[str] = []

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
        self.stream_call_count += 1
        self.call_count += 1
        self.received_requests.append(request)

        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)

        if self.error_to_raise and self.fail_after_n_chunks == 0:
            raise self.error_to_raise

        tokens = self.response_text.split(" ")
        for i, token in enumerate(tokens):
            if self.fail_after_n_chunks > 0 and i >= self.fail_after_n_chunks:
                if self.error_to_raise:
                    raise self.error_to_raise

            yield LLMStreamChunk(
                request_id=request.request_id,
                bot=request.selected_bot,
                text_delta=token + (" " if i < len(tokens) - 1 else ""),
                sequence=i,
                timestamp=datetime.now(timezone.utc),
                is_final=False,
            )

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        self.received_requests.append(request)

        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)

        if self.error_to_raise:
            raise self.error_to_raise

        return LLMResponse(
            request_id=request.request_id,
            bot=request.selected_bot,
            text=self.response_text,
            model="test-model",
            provider=self.name,
            latency_ms=10.0,
            first_token_latency_ms=5.0,
            timestamp=datetime.now(timezone.utc),
        )

    async def cancel(self, request_id: str) -> None:
        self.cancelled_request_ids.append(request_id)

    async def health_check(self) -> bool:
        return True


def make_sample_request(req_id: str = "req-1", user_msg: str = "AI kya hota hai?") -> LLMRequest:
    return LLMRequest(
        request_id=req_id,
        room_id="test-room",
        participant_identity="human-rahul",
        selected_bot=BotType.DOST,
        turn_id="turn-1",
        user_message=user_msg,
        system_prompt="You are AI Dost, a friendly companion.",
        context_messages=[{"role": "user", "content": "Hello"}],
        speaker_facts=["Name: Rahul", "Likes: Cricket"],
    )


# ==============================================================================
# 27 VERIFICATION SCENARIO TESTS (Section 19)
# ==============================================================================

@pytest.mark.asyncio
async def test_01_gemini_success_nvidia_not_called():
    """1. Gemini success -> NVIDIA NOT called."""
    gemini = DeterministicTestProvider(name="gemini", response_text="Gemini success")
    nvidia = DeterministicTestProvider(name="nvidia", response_text="NVIDIA response")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    resp = await mgr.generate(make_sample_request())
    assert resp.text == "Gemini success"
    assert resp.provider == "gemini"
    assert gemini.call_count == 1
    assert nvidia.call_count == 0


@pytest.mark.asyncio
async def test_02_gemini_quota_exhausted_nvidia_called():
    """2. Gemini quota exhausted -> NVIDIA called."""
    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.QUOTA_EXHAUSTED, retryable=True, message="Quota limit reached", status_code=429),
    )
    nvidia = DeterministicTestProvider(name="nvidia", response_text="NVIDIA fallback reply")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    resp = await mgr.generate(make_sample_request())
    assert resp.text == "NVIDIA fallback reply"
    assert resp.provider == "nvidia"
    assert gemini.call_count == 1
    assert nvidia.call_count == 1


@pytest.mark.asyncio
async def test_03_gemini_429_rate_limit_nvidia_called():
    """3. Gemini 429 -> NVIDIA called."""
    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.RATE_LIMIT, retryable=True, message="Too Many Requests", status_code=429),
    )
    nvidia = DeterministicTestProvider(name="nvidia", response_text="Recovered from 429")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    resp = await mgr.generate(make_sample_request())
    assert resp.text == "Recovered from 429"
    assert gemini.call_count == 1
    assert nvidia.call_count == 1


@pytest.mark.asyncio
async def test_04_gemini_temporary_503_nvidia_called():
    """4. Gemini temporary 503 -> NVIDIA called."""
    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.SERVICE_UNAVAILABLE, retryable=True, message="Service Unavailable", status_code=503),
    )
    nvidia = DeterministicTestProvider(name="nvidia", response_text="Recovered from 503")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    resp = await mgr.generate(make_sample_request())
    assert resp.text == "Recovered from 503"
    assert gemini.call_count == 1
    assert nvidia.call_count == 1


@pytest.mark.asyncio
async def test_05_gemini_timeout_nvidia_called():
    """5. Gemini timeout -> NVIDIA called if timeout fallback is enabled."""
    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=asyncio.TimeoutError(),
    )
    nvidia = DeterministicTestProvider(name="nvidia", response_text="Recovered from timeout")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    resp = await mgr.generate(make_sample_request())
    assert resp.text == "Recovered from timeout"
    assert gemini.call_count == 1
    assert nvidia.call_count == 1


@pytest.mark.asyncio
async def test_06_gemini_authentication_error_nvidia_not_called():
    """6. Gemini authentication error -> NVIDIA NOT called."""
    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.AUTHENTICATION, retryable=False, message="Invalid API key", status_code=401),
    )
    nvidia = DeterministicTestProvider(name="nvidia", response_text="Should not be called")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    with pytest.raises(ProviderError) as exc_info:
        await mgr.generate(make_sample_request())

    assert exc_info.value.category == ErrorCategory.AUTHENTICATION
    assert not exc_info.value.retryable
    assert gemini.call_count == 1
    assert nvidia.call_count == 0


@pytest.mark.asyncio
async def test_07_gemini_invalid_request_nvidia_not_called():
    """7. Gemini invalid request -> NVIDIA NOT called."""
    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.INVALID_REQUEST, retryable=False, message="Malformed JSON body", status_code=400),
    )
    nvidia = DeterministicTestProvider(name="nvidia", response_text="Should not be called")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    with pytest.raises(ProviderError) as exc_info:
        await mgr.generate(make_sample_request())

    assert exc_info.value.category == ErrorCategory.INVALID_REQUEST
    assert gemini.call_count == 1
    assert nvidia.call_count == 0


@pytest.mark.asyncio
async def test_08_gemini_invalid_model_nvidia_not_called():
    """8. Gemini invalid model -> NVIDIA NOT called."""
    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.INVALID_MODEL, retryable=False, message="Model not found", status_code=404),
    )
    nvidia = DeterministicTestProvider(name="nvidia", response_text="Should not be called")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    with pytest.raises(ProviderError) as exc_info:
        await mgr.generate(make_sample_request())

    assert exc_info.value.category == ErrorCategory.INVALID_MODEL
    assert gemini.call_count == 1
    assert nvidia.call_count == 0


@pytest.mark.asyncio
async def test_09_nvidia_success_after_gemini_failure_one_canonical_response():
    """9. NVIDIA success after Gemini failure -> one canonical response."""
    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.RATE_LIMIT, retryable=True, message="Rate limited", status_code=429),
    )
    nvidia = DeterministicTestProvider(name="nvidia", response_text="Clean canonical answer")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    req = make_sample_request()
    resp = await mgr.generate(req)
    assert resp.text == "Clean canonical answer"
    assert resp.provider == "nvidia"

    meta = mgr.get_metadata(req.request_id)
    assert meta is not None
    assert meta["fallback_triggered"] is True
    assert meta["final_provider"] == "nvidia"
    assert meta["primary_failure_category"] == ErrorCategory.RATE_LIMIT


@pytest.mark.asyncio
async def test_10_gemini_failure_plus_nvidia_failure_normalized_final_error():
    """10. Gemini failure + NVIDIA failure -> normalized final error."""
    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.RATE_LIMIT, retryable=True, message="Gemini 429", status_code=429),
    )
    nvidia = DeterministicTestProvider(
        name="nvidia",
        error_to_raise=ProviderError("nvidia", ErrorCategory.SERVICE_UNAVAILABLE, retryable=True, message="NVIDIA 503", status_code=503),
    )
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    with pytest.raises(ProviderError) as exc_info:
        await mgr.generate(make_sample_request())

    assert exc_info.value.provider == "nvidia"
    assert exc_info.value.category == ErrorCategory.SERVICE_UNAVAILABLE
    assert gemini.call_count == 1
    assert nvidia.call_count == 1


@pytest.mark.asyncio
async def test_11_no_fallback_loop():
    """11. No fallback loop (Gemini -> NVIDIA -> Gemini blocked)."""
    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.RATE_LIMIT, retryable=True, message="Gemini 429", status_code=429),
    )
    nvidia = DeterministicTestProvider(
        name="nvidia",
        error_to_raise=ProviderError("nvidia", ErrorCategory.RATE_LIMIT, retryable=True, message="NVIDIA 429", status_code=429),
    )
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    with pytest.raises(ProviderError):
        await mgr.generate(make_sample_request())

    assert gemini.call_count == 1, "Gemini should NOT be retried after NVIDIA fails"
    assert nvidia.call_count == 1


@pytest.mark.asyncio
async def test_12_maximum_two_provider_attempts():
    """12. Maximum two provider attempts per user turn."""
    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.QUOTA_EXHAUSTED, retryable=True, message="Quota", status_code=429),
    )
    nvidia = DeterministicTestProvider(
        name="nvidia",
        error_to_raise=ProviderError("nvidia", ErrorCategory.CONNECTION_FAILURE, retryable=True, message="Conn", status_code=500),
    )
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    with pytest.raises(ProviderError):
        await mgr.generate(make_sample_request())

    total_attempts = gemini.call_count + nvidia.call_count
    assert total_attempts == 2


@pytest.mark.asyncio
async def test_13_same_llm_request_reaches_gemini_and_nvidia():
    """13. Same LLM request reaches Gemini and NVIDIA."""
    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.QUOTA_EXHAUSTED, retryable=True, message="Quota", status_code=429),
    )
    nvidia = DeterministicTestProvider(name="nvidia", response_text="OK")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    req = make_sample_request(user_msg="Specific test query")
    await mgr.generate(req)

    assert len(gemini.received_requests) == 1
    assert len(nvidia.received_requests) == 1
    assert gemini.received_requests[0].user_message == "Specific test query"
    assert nvidia.received_requests[0].user_message == "Specific test query"
    assert gemini.received_requests[0].request_id == nvidia.received_requests[0].request_id


@pytest.mark.asyncio
async def test_14_conversation_context_is_preserved():
    """14. Conversation context is preserved."""
    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.RATE_LIMIT, retryable=True, message="429", status_code=429),
    )
    nvidia = DeterministicTestProvider(name="nvidia", response_text="Context preserved")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    req = make_sample_request()
    req.context_messages = [
        {"role": "user", "content": "Rahul: AI kya hai?"},
        {"role": "model", "content": "AI Dost: Machine intelligence."},
    ]

    await mgr.generate(req)
    assert nvidia.received_requests[0].context_messages == req.context_messages


@pytest.mark.asyncio
async def test_15_speaker_specific_context_is_preserved():
    """15. Speaker-specific context is preserved."""
    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.RATE_LIMIT, retryable=True, message="429", status_code=429),
    )
    nvidia = DeterministicTestProvider(name="nvidia", response_text="Facts preserved")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    req = make_sample_request()
    req.speaker_facts = ["Name: Rahul", "Role: Software Engineer", "Prefers: Hinglish"]

    await mgr.generate(req)
    assert nvidia.received_requests[0].speaker_facts == ["Name: Rahul", "Role: Software Engineer", "Prefers: Hinglish"]


@pytest.mark.asyncio
async def test_16_persona_is_preserved():
    """16. Persona is preserved."""
    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.RATE_LIMIT, retryable=True, message="429", status_code=429),
    )
    nvidia = DeterministicTestProvider(name="nvidia", response_text="Persona preserved")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    req = make_sample_request()
    req.selected_bot = BotType.SATHI
    req.system_prompt = "You are RoxStar AI Sathi, a supportive Indian female companion."

    await mgr.generate(req)
    assert nvidia.received_requests[0].selected_bot == BotType.SATHI
    assert nvidia.received_requests[0].system_prompt == req.system_prompt


@pytest.mark.asyncio
async def test_17_turn_lock_remains_correct_during_fallback(monkeypatch):
    """17. Turn lock remains correct during fallback (held throughout, released at end)."""
    room = "test-lock-sc17"
    await turn_lock_manager.release(room)

    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.QUOTA_EXHAUSTED, retryable=True, message="Quota", status_code=429),
    )
    nvidia = DeterministicTestProvider(name="nvidia", response_text="Turn lock response")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    monkeypatch.setattr("app.services.orchestrator.get_llm_provider", lambda: mgr)
    svc = OrchestratorService()

    from app.schemas.contracts import TranscriptEvent
    evt = TranscriptEvent(
        event_id="evt-lock-17",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="AI kya hota hai?",
        status="final",
    )

    dec = await svc.handle_transcript_event(evt)
    assert dec is not None
    assert dec.turn_lock_acquired is True

    ai_resp = await svc.await_llm_response(dec.turn_id, timeout=5.0)
    assert ai_resp is not None
    assert ai_resp.text == "Turn lock response"

    # Verify lock released in finally block
    lock_info = await turn_lock_manager.current_lock(room)
    assert lock_info is None


@pytest.mark.asyncio
async def test_18_turn_lock_releases_if_both_providers_fail(monkeypatch):
    """18. Turn lock releases if both providers fail."""
    room = "test-lock-sc18"
    await turn_lock_manager.release(room)

    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.QUOTA_EXHAUSTED, retryable=True, message="Quota", status_code=429),
    )
    nvidia = DeterministicTestProvider(
        name="nvidia",
        error_to_raise=ProviderError("nvidia", ErrorCategory.SERVICE_UNAVAILABLE, retryable=True, message="503", status_code=503),
    )
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    monkeypatch.setattr("app.services.orchestrator.get_llm_provider", lambda: mgr)
    svc = OrchestratorService()

    from app.schemas.contracts import TranscriptEvent
    evt = TranscriptEvent(
        event_id="evt-lock-18",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="AI kya hota hai?",
        status="final",
    )

    dec = await svc.handle_transcript_event(evt)
    assert dec is not None

    # Wait for completion task
    await svc.await_llm_response(dec.turn_id, timeout=5.0)

    # Verify lock is cleanly released
    lock_info = await turn_lock_manager.current_lock(room)
    assert lock_info is None


@pytest.mark.asyncio
async def test_19_cancellation_prevents_fallback():
    """19. Cancellation prevents fallback."""
    gemini = DeterministicTestProvider(
        name="gemini",
        delay_seconds=0.5,
        error_to_raise=asyncio.CancelledError(),
    )
    nvidia = DeterministicTestProvider(name="nvidia", response_text="Should not run")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    req = make_sample_request()
    await mgr.cancel(req.request_id)

    chunks = []
    async for c in mgr.stream(req):
        chunks.append(c)

    assert len(chunks) == 0
    assert nvidia.call_count == 0


@pytest.mark.asyncio
async def test_20_streaming_produces_one_canonical_final_response():
    """20. Streaming produces one canonical final response."""
    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.QUOTA_EXHAUSTED, retryable=True, message="429", status_code=429),
    )
    nvidia = DeterministicTestProvider(name="nvidia", response_text="Ek simple jawaab")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    chunks = []
    async for c in mgr.stream(make_sample_request()):
        chunks.append(c.text_delta)

    full = "".join(chunks).strip()
    assert full == "Ek simple jawaab"
    assert nvidia.stream_call_count == 1


@pytest.mark.asyncio
async def test_21_no_duplicate_response_publication(monkeypatch):
    """21. No duplicate response publication."""
    room = "test-sc21"
    await turn_lock_manager.release(room)

    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.QUOTA_EXHAUSTED, retryable=True, message="Quota", status_code=429),
    )
    nvidia = DeterministicTestProvider(name="nvidia", response_text="Only one response published")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=True)

    monkeypatch.setattr("app.services.orchestrator.get_llm_provider", lambda: mgr)
    svc = OrchestratorService()

    published_messages = []

    async def mock_broadcast(rm, payload):
        published_messages.append(payload)

    monkeypatch.setattr(svc, "_broadcast_to_livekit_room", mock_broadcast)

    from app.schemas.contracts import TranscriptEvent
    evt = TranscriptEvent(
        event_id="evt-21",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="AI kya hota hai?",
        status="final",
    )
    dec = await svc.handle_transcript_event(evt)
    await svc.await_llm_response(dec.turn_id, timeout=5.0)

    # Count canonical ai.response messages in broadcasts
    import json
    canonical_count = 0
    for p in published_messages:
        try:
            data = json.loads(p.decode("utf-8"))
            if data.get("type") == "ai.response":
                canonical_count += 1
        except Exception:
            pass

    assert canonical_count == 1


@pytest.mark.asyncio
async def test_22_fallback_disabled_nvidia_not_called():
    """22. fallback disabled (LLM_ENABLE_FALLBACK=false) -> NVIDIA NOT called."""
    gemini = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError("gemini", ErrorCategory.QUOTA_EXHAUSTED, retryable=True, message="Quota", status_code=429),
    )
    nvidia = DeterministicTestProvider(name="nvidia", response_text="Should not be called")
    mgr = LLMProviderManager(primary_provider=gemini, fallback_provider=nvidia, fallback_enabled=False)

    with pytest.raises(ProviderError):
        await mgr.generate(make_sample_request())

    assert gemini.call_count == 1
    assert nvidia.call_count == 0


def test_23_nvidia_only_mode_works(monkeypatch):
    """23. NVIDIA-only mode works."""
    monkeypatch.setattr(settings, "llm_primary_provider", "nvidia")
    monkeypatch.setattr(settings, "llm_enable_fallback", False)
    monkeypatch.setattr(settings, "nvidia_api_key", "nv-test-key")

    provider = get_llm_provider(provider_override="nvidia", api_key_override="nv-test-key")
    assert isinstance(provider, NVIDIAProvider)
    assert provider.name == "nvidia"


def test_24_gemini_only_mode_works(monkeypatch):
    """24. Gemini-only mode works."""
    monkeypatch.setattr(settings, "llm_primary_provider", "gemini")
    monkeypatch.setattr(settings, "llm_enable_fallback", False)

    provider = get_llm_provider(provider_override="gemini", api_key_override="gemini-test-key")
    assert isinstance(provider, GeminiLLMProvider)
    assert provider.name == "gemini"


def test_25_unknown_provider_fails_clearly():
    """25. Unknown provider fails clearly."""
    with pytest.raises(ValueError) as exc_info:
        create_concrete_provider("claude-ai")

    assert "Unsupported LLM provider" in str(exc_info.value)
    assert "claude-ai" in str(exc_info.value)


def test_26_missing_nvidia_configuration_handled_clearly(monkeypatch):
    """26. Missing NVIDIA configuration is handled clearly without startup crash."""
    monkeypatch.setattr(settings, "llm_primary_provider", "gemini")
    monkeypatch.setattr(settings, "llm_fallback_provider", "nvidia")
    monkeypatch.setattr(settings, "llm_enable_fallback", True)
    monkeypatch.setattr(settings, "nvidia_api_key", None)
    monkeypatch.setattr(settings, "gemini_api_key", "valid-gemini-key")

    # App factory creates manager with fallback_provider=None gracefully
    mgr = get_llm_provider()
    assert isinstance(mgr, LLMProviderManager)
    assert mgr.fallback_provider is None  # Reported unavailable without crashing


def test_27_existing_gemini_provider_structure_verified():
    """27. Existing Gemini provider functionality verified."""
    provider = GeminiLLMProvider(api_key="gemini-test-key")
    assert provider.name == "gemini"
    assert provider.default_model == settings.llm_model
    assert hasattr(provider, "generate")
    assert hasattr(provider, "stream")
    assert hasattr(provider, "cancel")
    assert hasattr(provider, "health_check")
