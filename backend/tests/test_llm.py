"""
Comprehensive Test Suite for Phase 3C: LLM Response Generation, Personas,
Prompt Architecture, Output Validation, Turn Lock Integration, and Assignment Scenarios.
"""

import asyncio
import os
import pytest
from datetime import datetime, timezone
from typing import List

from app.config import settings
from app.schemas.contracts import (
    BotType,
    ConversationTurn,
    OrchestrationDecision,
    ResponseEligibility,
    BotRoutingDecision,
    TranscriptEvent,
    TriggerType,
    TurnState,
)
from app.schemas.llm import LLMRequest, LLMStatus
from app.services.conversation_context import (
    ContextSnapshot,
    ConversationContextManager,
    RoomContextSnapshot,
    SpeakerProfile,
)
from app.services.conversation_context_builder import ConversationContextBuilder
from app.services.llm.factory import get_llm_provider
from app.services.llm.gemini_provider import GeminiLLMProvider
from app.services.llm.mock_provider import MockLLMProvider
from app.services.llm.output_validator import OutputValidator
from app.services.orchestrator import OrchestratorService
from app.services.personas.dost import AI_DOST_SYSTEM_INSTRUCTIONS
from app.services.personas.prompt_builder import PersonaPromptBuilder
from app.services.personas.sathi import AI_SATHI_SYSTEM_INSTRUCTIONS
from app.services.turn_lock import turn_lock_manager


# ==============================================================================
# 1. PROVIDER & STREAMING TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_mock_provider_generation_and_streaming():
    """Verifies that MockLLMProvider yields streaming chunks and aggregates clean responses."""
    provider = MockLLMProvider()
    req = LLMRequest(
        request_id="req-test-1",
        room_id="room-1",
        participant_identity="rahul",
        selected_bot=BotType.DOST,
        turn_id="turn-1",
        user_message="AI kya hota hai?",
        system_prompt="You are Dost.",
    )

    chunks = []
    async for chunk in provider.stream(req):
        assert chunk.request_id == "req-test-1"
        assert chunk.bot == BotType.DOST
        chunks.append(chunk.text_delta)

    full_text = "".join(chunks)
    assert "ai" in full_text.lower() or "technology" in full_text.lower()

    # Non-streaming generate
    resp = await provider.generate(req)
    assert resp.bot == BotType.DOST
    assert resp.text == full_text.strip()
    assert resp.latency_ms >= 0


@pytest.mark.asyncio
async def test_mock_provider_cancellation():
    """Verifies that cancellation halts stream consumption."""
    provider = MockLLMProvider(chunk_delay_s=0.02)
    req = LLMRequest(
        request_id="req-cancel-1",
        room_id="room-1",
        participant_identity="rahul",
        selected_bot=BotType.DOST,
        turn_id="turn-1",
        user_message="Tell me a very long story about AI.",
        system_prompt="You are Dost.",
    )

    chunks_received = []

    async def consume_and_cancel():
        async for chunk in provider.stream(req):
            chunks_received.append(chunk.text_delta)
            if len(chunks_received) >= 2:
                await provider.cancel(req.request_id)

    await consume_and_cancel()
    # Ensure stream stopped early due to cancellation
    assert len(chunks_received) < 30


@pytest.mark.asyncio
async def test_mock_provider_simulated_errors():
    """Verifies simulated timeouts, 429 rate limits, and 500 server errors."""
    timeout_provider = MockLLMProvider(simulate_timeout=True)
    req = LLMRequest(
        request_id="req-err-1",
        room_id="room-1",
        participant_identity="rahul",
        selected_bot=BotType.DOST,
        turn_id="turn-1",
        user_message="Hello",
        system_prompt="",
    )
    with pytest.raises(TimeoutError):
        async for _ in timeout_provider.stream(req):
            pass

    rate_limit_provider = MockLLMProvider(simulate_rate_limit=True)
    with pytest.raises(RuntimeError, match="429"):
        async for _ in rate_limit_provider.stream(req):
            pass

    failure_provider = MockLLMProvider(simulate_failure=True)
    with pytest.raises(RuntimeError, match="500"):
        async for _ in failure_provider.stream(req):
            pass


@pytest.mark.asyncio
async def test_gemini_provider_structure_and_health():
    """Verifies GeminiLLMProvider initializes cleanly and guards against missing key."""
    # When initialized with no key and no env key
    prov_no_key = GeminiLLMProvider(api_key=None)
    assert await prov_no_key.health_check() is False

    # When initialized with test key
    prov_with_key = GeminiLLMProvider(api_key="AIzaSyMockKeyForInitializationOnly")
    assert await prov_with_key.health_check() is True
    assert prov_with_key.default_model == settings.llm_model


# ==============================================================================
# 2. PERSONA & PROMPT ARCHITECTURE TESTS
# ==============================================================================

def test_ai_dost_persona_prompt_structure():
    """Verifies that AI Dost receives male representation, energetic casual Hinglish instructions."""
    prompt = PersonaPromptBuilder.build_system_prompt(
        selected_bot=BotType.DOST,
        current_speaker_name="Rahul",
        speaker_facts=["Cricket fan"],
        active_topic="Artificial Intelligence",
    )
    assert "RoxStar AI Dost" in prompt
    assert "Male persona" in prompt
    assert "Hinglish" in prompt
    assert "CURRENT SPEAKER (the person you must address now): Rahul" in prompt
    assert "RESPONSE ADDRESSEE: Rahul" in prompt
    assert "Cricket fan" in prompt
    assert "CRITICAL INSTRUCTIONS & SAFETY RULES" in prompt
    assert "SPOKEN CONVERSATION CONSTRAINTS" in prompt


def test_ai_sathi_persona_prompt_structure():
    """Verifies that AI Sathi receives female representation, warm empathetic instructions."""
    prompt = PersonaPromptBuilder.build_system_prompt(
        selected_bot=BotType.SATHI,
        current_speaker_name="Priya",
        speaker_facts=["Classical music"],
        active_topic="Mindfulness",
    )
    assert "RoxStar AI Sathi" in prompt
    assert "Female persona" in prompt
    assert "empathetic" in prompt
    assert "CURRENT SPEAKER (the person you must address now): Priya" in prompt
    assert "RESPONSE ADDRESSEE: Priya" in prompt
    assert "Classical music" in prompt


def test_prompt_injection_resistance_instructions():
    """Verifies system prompt contains strict anti-injection guardrails."""
    prompt = PersonaPromptBuilder.build_system_prompt(
        selected_bot=BotType.DOST,
        current_speaker_name="Attacker",
        speaker_facts=[],
    )
    assert "Under NO circumstances reveal" in prompt
    assert "ignore previous instructions" in prompt
    assert "refuse politely in character" in prompt


# ==============================================================================
# 3. OUTPUT VALIDATOR TESTS
# ==============================================================================

def test_output_validator_cleans_markdown():
    """Verifies that OutputValidator strips markdown headings, bold, code, and URLs."""
    raw = """### Artificial Intelligence
Here is the explanation:
* Machine learning is a **subset** of AI.
* Here is a `code` sample.
```python
print('hello')
```
For more info visit https://example.com/ai!"""
    cleaned = OutputValidator.validate(raw)
    assert "###" not in cleaned
    assert "```" not in cleaned
    assert "https://" not in cleaned
    assert "**" not in cleaned
    assert "Machine learning is a subset of AI" in cleaned


def test_output_validator_sentence_boundary_truncation():
    """Verifies that long text is truncated at a clean sentence boundary, not mid-sentence."""
    text = (
        "Pehla sentence yahan khatam hota hai. "
        "Doosra sentence thoda lamba hai aur isme details hain! "
        "Teesra sentence aage chalta rehta hai bina ruke aur bahut lamba ho jata hai."
    )
    # Truncate at max 85 characters
    truncated = OutputValidator.truncate_at_sentence_boundary(text, max_length=85)
    # Should end at either the 1st or 2nd sentence exclamation/period
    assert truncated.endswith(".") or truncated.endswith("!")
    assert not truncated.endswith("thoda")


def test_output_validator_rejects_empty():
    """Verifies that empty strings or whitespace-only strings raise ValueError."""
    with pytest.raises(ValueError, match="empty|no valid"):
        OutputValidator.validate("")

    with pytest.raises(ValueError, match="empty|no valid"):
        OutputValidator.validate("   \n\t  ")


# ==============================================================================
# 4. CONVERSATION CONTEXT BUILDER & SPEAKER ATTRIBUTION
# ==============================================================================

def test_context_builder_preserves_speaker_isolation():
    """Verifies Rahul's facts and Priya's facts are never conflated."""
    ctx_mgr = ConversationContextManager()
    t1 = ConversationTurn(
        turn_id="t1",
        room_id="room-test",
        participant_identity="rahul",
        participant_display_name="Rahul",
        transcript="Mera naam Rahul hai aur mujhe cricket pasand hai.",
        state=TurnState.COMPLETE,
        is_final=True,
    )
    t2 = ConversationTurn(
        turn_id="t2",
        room_id="room-test",
        participant_identity="priya",
        participant_display_name="Priya",
        transcript="Mujhe reading aur music pasand hai.",
        state=TurnState.COMPLETE,
        is_final=True,
    )

    snap = ContextSnapshot(
        snapshot_id="s1",
        room_id="room-test",
        recent_turns=[t1, t2],
        all_speaker_profiles={
            "rahul": SpeakerProfile(participant_id="rahul", name="Rahul", facts=["Cricket"]),
            "priya": SpeakerProfile(participant_id="priya", name="Priya", facts=["Reading", "Music"]),
        },
        current_topic="Introductions",
    )

    dec = OrchestrationDecision(
        decision_id="d1",
        room_id="room-test",
        turn_id="t3",
        eligibility=ResponseEligibility(should_respond=True, confidence=1.0, trigger_type=TriggerType.DIRECT_QUESTION, reason="question"),
        routing=BotRoutingDecision(decision_id="r1", room_id="room-test", turn_id="t3", selected_bot=BotType.DOST, reason="tech", confidence=1.0, routing_source="explicit_rule"),
    )

    t3 = ConversationTurn(
        turn_id="t3",
        room_id="room-test",
        participant_identity="rahul",
        participant_display_name="Rahul",
        transcript="Maine tumhe kya bataya tha?",
        state=TurnState.COMPLETE,
        is_final=True,
    )

    req = ConversationContextBuilder.build_request(dec, snap, t3)

    # Current speaker facts must ONLY have Rahul's cricket
    assert "Cricket" in req.speaker_facts
    assert "Reading" not in req.speaker_facts

    # Other speaker facts summary mentions Priya
    assert "Priya: Reading, Music" in req.system_prompt


def test_context_builder_bounded_turn_window():
    """Verifies that context builder retains at most MAX_CONTEXT_TURNS."""
    turns = [
        ConversationTurn(
            turn_id=f"t-{i}",
            room_id="room-bounded",
            participant_identity="rahul",
            participant_display_name="Rahul",
            transcript=f"Turn number {i}",
            state=TurnState.COMPLETE,
            is_final=True,
        )
        for i in range(15)
    ]
    snap = ContextSnapshot(
        snapshot_id="snap-b",
        room_id="room-bounded",
        recent_turns=turns,
        all_speaker_profiles={},
    )
    dec = OrchestrationDecision(
        decision_id="d-b",
        room_id="room-bounded",
        turn_id="t-15",
        eligibility=ResponseEligibility(should_respond=True, confidence=1.0, trigger_type=TriggerType.DIRECT_QUESTION, reason="test"),
        routing=BotRoutingDecision(decision_id="r-b", room_id="room-bounded", turn_id="t-15", selected_bot=BotType.DOST, reason="test", confidence=1.0, routing_source="fallback"),
    )
    t_curr = ConversationTurn(
        turn_id="t-15",
        room_id="room-bounded",
        participant_identity="rahul",
        participant_display_name="Rahul",
        transcript="Final turn",
        state=TurnState.COMPLETE,
        is_final=True,
    )

    req = ConversationContextBuilder.build_request(dec, snap, t_curr, max_context_turns=6)
    assert len(req.context_messages) == 6
    assert "Turn number 14" in req.context_messages[-1]["content"]


# ==============================================================================
# 5. ORCHESTRATOR INTEGRATION & TURN LOCK TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_orchestrator_generates_ai_response_and_releases_lock():
    """Verifies end-to-end LLM generation downstream of turn lock and guaranteed finally lock release."""
    svc = OrchestratorService()
    room = "test-orch-llm-1"
    await turn_lock_manager.release(room)

    evt = TranscriptEvent(
        event_id="evt-llm-1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="AI kya hota hai?",
        status="final",
    )

    dec = await svc.handle_transcript_event(evt)
    assert dec is not None
    assert dec.eligibility.should_respond is True
    assert dec.routing.selected_bot == BotType.DOST
    assert dec.turn_lock_acquired is True

    # Await background LLM generation
    ai_resp = await svc.await_llm_response(dec.turn_id, timeout=5.0)
    assert ai_resp is not None
    assert ai_resp.bot == BotType.DOST
    assert ai_resp.responding_to_turn_id == dec.turn_id
    assert len(ai_resp.text) > 10

    # Lock must be RELEASED in finally
    lock_info = await turn_lock_manager.current_lock(room)
    assert lock_info is None


@pytest.mark.asyncio
async def test_orchestrator_idempotency_duplicate_turns():
    """Verifies that duplicate turns do not trigger multiple LLM requests."""
    svc = OrchestratorService()
    room = "test-orch-idempotency"
    await turn_lock_manager.release(room)

    evt = TranscriptEvent(
        event_id="evt-idemp-1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="What is cloud computing?",
        status="final",
    )

    # First delivery
    dec1 = await svc.handle_transcript_event(evt)
    assert dec1 is not None

    # Wait for completion
    ai_resp1 = await svc.await_llm_response(dec1.turn_id, timeout=5.0)
    assert ai_resp1 is not None

    # Duplicate delivery with same event_id
    dec2 = await svc.handle_transcript_event(evt)
    # Turn detector suppresses duplicate event
    assert dec2 is None


@pytest.mark.asyncio
async def test_orchestrator_race_free_cancellation():
    """Verifies cancellation prevents late response publication."""
    svc = OrchestratorService()
    room = "test-orch-cancel"
    await turn_lock_manager.release(room)

    # Mark cancellation before response completes
    evt = TranscriptEvent(
        event_id="evt-cancel-1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="Tell me an extremely detailed story about quantum computing.",
        status="final",
    )

    # We register a listener that immediately cancels on request start
    def on_event(oevt):
        if oevt.event_type.value == "LLM_REQUEST_STARTED":
            req_id = oevt.payload.get("request_id")
            if req_id:
                asyncio.create_task(svc.cancel_generation(req_id))

    svc.register_listener(on_event)

    dec = await svc.handle_transcript_event(evt)
    assert dec is not None

    ai_resp = await svc.await_llm_response(dec.turn_id, timeout=2.0)
    # Publication suppressed
    assert ai_resp is None

    # Turn lock must be released
    lock_info = await turn_lock_manager.current_lock(room)
    assert lock_info is None


# ==============================================================================
# 6. ASSIGNMENT SCENARIOS 1–5 TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_assignment_scenario_1_ai_explanation():
    """Scenario 1: 'AI kya hota hai?' -> Natural conversational Hindi/Hinglish answer."""
    svc = OrchestratorService()
    room = "test-sc1"
    await turn_lock_manager.release(room)

    evt = TranscriptEvent(
        event_id="evt-llm-sc1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="AI kya hota hai?",
        status="final",
    )
    dec = await svc.handle_transcript_event(evt)
    ai_resp = await svc.await_llm_response(dec.turn_id, timeout=5.0)
    assert ai_resp is not None
    assert any(k in ai_resp.text.lower() for k in ["ai", "technology", "machines", "human"])


@pytest.mark.asyncio
async def test_assignment_scenario_2_cloud_computing_english_understood():
    """Scenario 2: 'What is cloud computing?' -> English understood, natural Hindi/Hinglish reply."""
    svc = OrchestratorService()
    room = "test-sc2"
    await turn_lock_manager.release(room)

    evt = TranscriptEvent(
        event_id="evt-llm-sc2",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="What is cloud computing?",
        status="final",
    )
    dec = await svc.handle_transcript_event(evt)
    ai_resp = await svc.await_llm_response(dec.turn_id, timeout=5.0)
    assert ai_resp is not None
    assert any(k in ai_resp.text.lower() for k in ["cloud", "internet", "data", "store"])


@pytest.mark.asyncio
async def test_assignment_scenario_3_srk_follow_up_pronoun_resolution():
    """Scenario 3: 'Shah Rukh Khan kaun hai?' -> 'Unki koi famous movie batao.' -> Pronoun resolved."""
    svc = OrchestratorService()
    room = "test-sc3"
    await turn_lock_manager.release(room)

    # Turn 1
    evt1 = TranscriptEvent(
        event_id="evt-llm-sc3-1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="Shah Rukh Khan kaun hai?",
        status="final",
    )
    dec1 = await svc.handle_transcript_event(evt1)
    await svc.await_llm_response(dec1.turn_id, timeout=5.0)

    # Turn 2: Follow-up with pronoun "Unki"
    evt2 = TranscriptEvent(
        event_id="evt-llm-sc3-2",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="Unki koi famous movie batao.",
        status="final",
    )
    dec2 = await svc.handle_transcript_event(evt2)
    ai_resp2 = await svc.await_llm_response(dec2.turn_id, timeout=5.0)
    assert ai_resp2 is not None
    assert any(k in ai_resp2.text.lower() for k in ["dilwale", "swades", "movie", "film", "shah rukh"])


@pytest.mark.asyncio
async def test_assignment_scenario_4_multi_user_priya_followup():
    """Scenario 4: Rahul: 'AI kya hota hai?' -> Priya: 'Thoda aur simple batao.' -> Priya gets simpler explanation of AI."""
    svc = OrchestratorService()
    room = "test-sc4"
    await turn_lock_manager.release(room)

    # Turn 1: Rahul
    evt1 = TranscriptEvent(
        event_id="evt-llm-sc4-1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="AI kya hota hai?",
        status="final",
    )
    dec1 = await svc.handle_transcript_event(evt1)
    await svc.await_llm_response(dec1.turn_id, timeout=5.0)

    # Turn 2: Priya asks simpler explanation
    evt2 = TranscriptEvent(
        event_id="evt-llm-sc4-2",
        room_id=room,
        participant_identity="human-priya",
        participant_display_name="Priya",
        transcript="Thoda aur simple batao.",
        status="final",
    )
    dec2 = await svc.handle_transcript_event(evt2)
    ai_resp2 = await svc.await_llm_response(dec2.turn_id, timeout=5.0)
    assert ai_resp2 is not None
    assert any(k in ai_resp2.text.lower() for k in ["aasan", "saral", "simple", "computer", "brain"])


@pytest.mark.asyncio
async def test_assignment_scenario_5_speaker_memory_facts():
    """Scenario 5: Rahul: 'Mera naam Rahul hai.' 'Mujhe cricket pasand hai.' -> 'Maine tumhe kya bataya tha?'"""
    svc = OrchestratorService()
    room = "test-sc5"
    await turn_lock_manager.release(room)

    # Turn 1: Name and cricket interest
    evt1 = TranscriptEvent(
        event_id="evt-llm-sc5-1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="Mera naam Rahul hai aur mujhe cricket pasand hai.",
        status="final",
    )
    dec1 = await svc.handle_transcript_event(evt1)
    await svc.await_llm_response(dec1.turn_id, timeout=5.0)

    # Turn 2: Query memory
    evt2 = TranscriptEvent(
        event_id="evt-llm-sc5-2",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="Maine tumhe kya bataya tha?",
        status="final",
    )
    dec2 = await svc.handle_transcript_event(evt2)
    ai_resp2 = await svc.await_llm_response(dec2.turn_id, timeout=5.0)
    assert ai_resp2 is not None
    assert "cricket" in ai_resp2.text.lower()


# ==============================================================================
# 7. OPT-IN REAL GEMINI SMOKE TEST (Requirement 8)
# ==============================================================================

@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_LLM_LIVE_TEST") != "true" or not settings.effective_gemini_api_key,
    reason="Opt-in real Gemini test requires RUN_LLM_LIVE_TEST=true and valid GEMINI_API_KEY",
)
async def test_real_gemini_live_smoke_test():
    """
    Opt-in smoke test verifying live connectivity to Google Gemini API via official google-genai SDK.
    Runs only when RUN_LLM_LIVE_TEST=true and a non-placeholder GEMINI_API_KEY is configured.
    """
    provider = GeminiLLMProvider(default_model="gemini-2.5-flash")
    req = LLMRequest(
        request_id="live-gemini-test",
        room_id="live-room",
        participant_identity="tester",
        selected_bot=BotType.DOST,
        turn_id="turn-live-1",
        user_message="AI kya hai? Ek sentence mein samjhao.",
        system_prompt=AI_DOST_SYSTEM_INSTRUCTIONS,
    )

    chunks = []
    async for chunk in provider.stream(req):
        chunks.append(chunk.text_delta)

    full_text = "".join(chunks).strip()
    assert len(full_text) > 5
    validated = OutputValidator.validate(full_text)
    assert len(validated) > 5
