"""
Controlled fallback smoke test (Requirement 21).
Injects a controlled retryable failure (quota_exhausted / 429) on Gemini primary
without wasting remote API quota, and verifies the full pipeline failover to NVIDIA.
"""

import json
import pytest

from app.config import settings
from app.schemas.contracts import BotType, ModalityType, TranscriptEvent
from app.services.llm.base import LLMProvider
from app.services.llm.errors import ErrorCategory, ProviderError
from app.services.llm.manager import LLMProviderManager
from app.services.orchestrator import OrchestratorService
from app.services.turn_lock import turn_lock_manager
from tests.test_llm_fallback import DeterministicTestProvider


@pytest.mark.asyncio
async def test_controlled_fallback_smoke(monkeypatch):
    """
    Controlled Failover Smoke Test:
    Demonstrates Gemini primary -> quota exhausted (429) -> NVIDIA fallback -> canonical response.
    Verifies:
    - fallback_triggered=True
    - final_provider='nvidia'
    - one canonical response
    - conversation context preserved
    - turn lock released correctly
    - no duplicate publication
    """
    room_id = "room-fallback-smoke"
    await turn_lock_manager.release(room_id)

    # 1. Setup injected primary provider that fails with quota_exhausted
    primary_mock = DeterministicTestProvider(
        name="gemini",
        error_to_raise=ProviderError(
            provider="gemini",
            category=ErrorCategory.QUOTA_EXHAUSTED,
            retryable=True,
            message="Google AI Studio quota limit exceeded (429 RESOURCE_EXHAUSTED)",
            status_code=429,
        ),
    )

    # 2. Setup fallback provider that generates the actual answer
    fallback_mock = DeterministicTestProvider(
        name="nvidia",
        response_text="Artificial Intelligence insaanon jaisi sochne samajhne wali machine technology hai.",
    )

    # 3. Create LLMProviderManager
    manager = LLMProviderManager(
        primary_provider=primary_mock,
        fallback_provider=fallback_mock,
        fallback_enabled=True,
    )

    # 4. Inject manager into orchestrator
    monkeypatch.setattr("app.services.orchestrator.get_llm_provider", lambda: manager)
    svc = OrchestratorService()

    broadcasts = []

    async def capture_broadcast(rm, payload):
        broadcasts.append((rm, payload))

    monkeypatch.setattr(svc, "_broadcast_to_livekit_room", capture_broadcast)

    # 5. Dispatch real TranscriptEvent through master pipeline
    event = TranscriptEvent(
        event_id="evt-fb-smoke-1",
        room_id=room_id,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="AI kya hota hai? Simple Hinglish mein batao.",
        status="final",
        modality=ModalityType.TEXT,
    )

    decision = await svc.handle_transcript_event(event)
    assert decision is not None
    assert decision.eligibility.should_respond is True
    assert decision.turn_lock_acquired is True

    # 6. Await generation
    ai_resp = await svc.await_llm_response(decision.turn_id, timeout=10.0)
    assert ai_resp is not None

    # 7. Verification Assertions:
    # A. Content
    assert ai_resp.text == "Artificial Intelligence insaanon jaisi sochne samajhne wali machine technology hai."

    # B. Metadata
    meta = manager.get_metadata(ai_resp.request_id)
    assert meta is not None
    assert meta["fallback_triggered"] is True
    assert meta["primary_failure_category"] == ErrorCategory.QUOTA_EXHAUSTED
    assert meta["final_provider"] == "nvidia"
    assert meta["primary_provider"] == "gemini"
    assert meta["fallback_provider"] == "nvidia"

    # C. Model & Provider
    assert ai_resp.provider == "nvidia"
    assert ai_resp.model == settings.nvidia_model

    # D. Provider invocation counts
    assert primary_mock.call_count == 1
    assert fallback_mock.call_count == 1

    # E. Context preserved
    assert len(fallback_mock.received_requests) == 1
    fb_req = fallback_mock.received_requests[0]
    assert fb_req.user_message == "Rahul: AI kya hota hai? Simple Hinglish mein batao."
    assert fb_req.selected_bot == BotType.DOST

    # F. Turn lock released correctly
    lock_info = await turn_lock_manager.current_lock(room_id)
    assert lock_info is None

    # G. Exactly ONE canonical response message published
    canonical_responses = []
    for rm, payload in broadcasts:
        try:
            data = json.loads(payload.decode("utf-8"))
            if data.get("type") == "ai.response":
                canonical_responses.append(data)
        except Exception:
            pass

    assert len(canonical_responses) == 1
    assert canonical_responses[0]["text"] == ai_resp.text
