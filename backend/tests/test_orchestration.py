import asyncio
import time
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.contracts import (
    BotType,
    ConversationTurn,
    ModalityType,
    OrchestrationDecision,
    ResponseEligibility,
    TranscriptEvent,
    TriggerType,
)
from app.services.bot_router import BotRouter
from app.services.conversation_context import (
    ContextSnapshot,
    ConversationContextManager,
)
from app.services.incomplete_utterance import is_incomplete_utterance
from app.services.orchestrator import OrchestratorService
from app.services.response_eligibility import ResponseEligibilityService
from app.services.stt_auth import generate_stt_token
from app.services.turn_detector import TurnDetector
from app.services.turn_lock import TurnLockManager, turn_lock_manager



# ============================================================================
# 1. TURN DETECTOR TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_partial_partial_final_is_one_turn():
    """Verify streaming partial -> partial -> final produces ONE unified turn."""
    detector = TurnDetector()
    room = "test-room-turn-1"
    speaker = "human-rahul"

    # Partials update the same turn
    evt1 = TranscriptEvent(
        event_id="evt-p1",
        room_id=room,
        participant_identity=speaker,
        participant_display_name="Rahul",
        transcript="AI kya",
        status="partial",
    )
    turn1, _ = await detector.process_transcript_event(evt1)
    assert turn1 is None

    evt2 = TranscriptEvent(
        event_id="evt-p2",
        room_id=room,
        participant_identity=speaker,
        participant_display_name="Rahul",
        transcript="AI kya hota",
        status="partial",
    )
    turn2, _ = await detector.process_transcript_event(evt2)
    assert turn2 is None

    # Final produces the completed turn
    evt3 = TranscriptEvent(
        event_id="evt-f1",
        room_id=room,
        participant_identity=speaker,
        participant_display_name="Rahul",
        transcript="AI kya hota hai?",
        status="final",
    )
    final_turn, events = await detector.process_transcript_event(evt3)
    assert final_turn is not None
    assert final_turn.transcript == "AI kya hota hai?"
    assert final_turn.participant_identity == speaker
    assert final_turn.is_complete is True
    assert any(e.event_type.value == "TURN_COMPLETED" for e in events)


@pytest.mark.asyncio
async def test_duplicate_final_transcript_ignored():
    """Verify duplicate final transcript event IDs are ignored."""
    detector = TurnDetector()
    room = "test-room-dup"
    speaker = "human-rahul"

    evt = TranscriptEvent(
        event_id="evt-dup-123",
        room_id=room,
        participant_identity=speaker,
        participant_display_name="Rahul",
        transcript="Hello world",
        status="final",
    )

    turn1, _ = await detector.process_transcript_event(evt)
    assert turn1 is not None

    # Duplicate submission of the same final event ID
    turn2, _ = await detector.process_transcript_event(evt)
    assert turn2 is None


@pytest.mark.asyncio
async def test_pause_continuation_single_turn():
    """
    Verify pause followed by continuation remains one logical turn.
    Example: 'Cloud computing kya hai...' [pause] '...aur iska use companies kaise karti hain?'
    """
    detector = TurnDetector()
    room = "test-room-pause"
    speaker = "human-rahul"

    evt1 = TranscriptEvent(
        event_id="evt-pause-p1",
        room_id=room,
        participant_identity=speaker,
        participant_display_name="Rahul",
        transcript="Cloud computing kya hai...",
        status="partial",
    )
    await detector.process_transcript_event(evt1)

    # Pause occurs
    pause_events = await detector.handle_pause_event(room, speaker)
    assert len(pause_events) == 1
    assert pause_events[0].event_type.value == "TURN_PAUSED"

    # Speaker resumes speaking within same turn
    evt2 = TranscriptEvent(
        event_id="evt-pause-p2",
        room_id=room,
        participant_identity=speaker,
        participant_display_name="Rahul",
        transcript="Cloud computing kya hai aur iska use companies kaise karti hain?",
        status="partial",
    )
    _, resume_events = await detector.process_transcript_event(evt2)
    assert any(e.event_type.value == "TURN_RESUMED" for e in resume_events)

    # Finalize
    evt_final = TranscriptEvent(
        event_id="evt-pause-f1",
        room_id=room,
        participant_identity=speaker,
        participant_display_name="Rahul",
        transcript="Cloud computing kya hai aur iska use companies kaise karti hain?",
        status="final",
    )
    final_turn, _ = await detector.process_transcript_event(evt_final)
    assert final_turn is not None
    assert "Cloud computing kya hai" in final_turn.transcript
    assert "companies kaise karti hain" in final_turn.transcript


@pytest.mark.asyncio
async def test_separate_speakers_separate_turns():
    """Verify distinct speakers maintain independent active turn states."""
    detector = TurnDetector()
    room = "test-room-multi-turn"

    evt_rahul = TranscriptEvent(
        event_id="evt-r1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="Main Rahul hoon",
        status="partial",
    )
    await detector.process_transcript_event(evt_rahul)

    evt_priya = TranscriptEvent(
        event_id="evt-p1",
        room_id=room,
        participant_identity="human-priya",
        participant_display_name="Priya",
        transcript="Main Priya hoon",
        status="partial",
    )
    await detector.process_transcript_event(evt_priya)

    # Both speakers have distinct active turns
    assert ("test-room-multi-turn", "human-rahul") in detector._active_turns
    assert ("test-room-multi-turn", "human-priya") in detector._active_turns
    assert detector._active_turns[("test-room-multi-turn", "human-rahul")].transcript == "Main Rahul hoon"
    assert detector._active_turns[("test-room-multi-turn", "human-priya")].transcript == "Main Priya hoon"


# ============================================================================
# 2. INCOMPLETE UTTERANCE HEURISTICS TESTS
# ============================================================================

def test_incomplete_utterance_heuristics():
    """Verify incomplete phrase stems and trailing conjunctions are flagged."""
    # Incomplete cases
    inc1, r1 = is_incomplete_utterance("AI kya...")
    assert inc1 is True
    assert "ellipsis" in r1

    inc2, r2 = is_incomplete_utterance("Cloud computing mein...")
    assert inc2 is True

    inc3, r3 = is_incomplete_utterance("Shah Rukh Khan ki...")
    assert inc3 is True

    inc4, r4 = is_incomplete_utterance("Cloud computing kya hai aur...")
    assert inc4 is True

    inc5, r5 = is_incomplete_utterance("AI kya")
    assert inc5 is True
    assert "question_marker" in r5

    # Complete cases
    c1, _ = is_incomplete_utterance("AI kya hota hai?")
    assert c1 is False

    c2, _ = is_incomplete_utterance("Machine learning simple language mein samjhao.")
    assert c2 is False

    c3, _ = is_incomplete_utterance("simple language mein samjhao")
    assert c3 is False


# ============================================================================
# 3. RESPONSE ELIGIBILITY TESTS
# ============================================================================

def test_response_eligibility_classification():
    service = ResponseEligibilityService()
    now = datetime.now(timezone.utc)

    # 1. Direct Question
    t_q = ConversationTurn(
        turn_id="t-1",
        room_id="r-1",
        participant_identity="human-1",
        participant_display_name="User",
        transcript="AI kya hota hai?",
        started_at=now,
        ended_at=now,
        is_complete=True,
    )
    e_q = service.evaluate(t_q)
    assert e_q.should_respond is True
    assert e_q.trigger_type == TriggerType.DIRECT_QUESTION

    # 2. Direct Request
    t_req = ConversationTurn(
        turn_id="t-2",
        room_id="r-1",
        participant_identity="human-1",
        participant_display_name="User",
        transcript="Machine learning simple language mein samjhao.",
        started_at=now,
        ended_at=now,
        is_complete=True,
    )
    e_req = service.evaluate(t_req)
    assert e_req.should_respond is True
    assert e_req.trigger_type == TriggerType.DIRECT_REQUEST

    # 3. Acknowledgement
    t_ack = ConversationTurn(
        turn_id="t-3",
        room_id="r-1",
        participant_identity="human-1",
        participant_display_name="User",
        transcript="Okay, samajh gaya.",
        started_at=now,
        ended_at=now,
        is_complete=True,
    )
    e_ack = service.evaluate(t_ack)
    assert e_ack.should_respond is False
    assert e_ack.trigger_type == TriggerType.ACKNOWLEDGEMENT

    # 4. Casual Statement
    t_cas = ConversationTurn(
        turn_id="t-4",
        room_id="r-1",
        participant_identity="human-1",
        participant_display_name="User",
        transcript="Kal college mein event hai.",
        started_at=now,
        ended_at=now,
        is_complete=True,
    )
    e_cas = service.evaluate(t_cas)
    assert e_cas.should_respond is False
    assert e_cas.trigger_type == TriggerType.CASUAL_STATEMENT

    # 5. Incomplete
    t_inc = ConversationTurn(
        turn_id="t-5",
        room_id="r-1",
        participant_identity="human-1",
        participant_display_name="User",
        transcript="Cloud computing kya...",
        started_at=now,
        ended_at=now,
        is_complete=True,
    )
    e_inc = service.evaluate(t_inc)
    assert e_inc.should_respond is False
    assert e_inc.trigger_type == TriggerType.INCOMPLETE_UTTERANCE


# ============================================================================
# 4. TWO-BOT ROUTER TESTS
# ============================================================================

def test_bot_routing_priority_and_single_bot():
    router = BotRouter()
    now = datetime.now(timezone.utc)

    # 1. Explicit Dost
    t_dost = ConversationTurn(
        turn_id="t-d1",
        room_id="r-route",
        participant_identity="h-1",
        participant_display_name="User",
        transcript="AI Dost, explain AI.",
        started_at=now,
        ended_at=now,
        is_complete=True,
    )
    e_yes = ResponseEligibility(
        should_respond=True,
        reason="explicit_bot_name",
        confidence=0.98,
        trigger_type=TriggerType.EXPLICIT_BOT_ADDRESS,
    )
    r_dost = router.route(t_dost, e_yes)
    assert r_dost.selected_bot == BotType.DOST
    assert r_dost.routing_source == "explicit_rule"

    # 2. Explicit Sathi
    t_sathi = ConversationTurn(
        turn_id="t-s1",
        room_id="r-route",
        participant_identity="h-1",
        participant_display_name="User",
        transcript="Sathi, explain AI.",
        started_at=now,
        ended_at=now,
        is_complete=True,
    )
    r_sathi = router.route(t_sathi, e_yes)
    assert r_sathi.selected_bot == BotType.SATHI
    assert r_sathi.routing_source == "explicit_rule"

    # 3. RoxStar Dost / RoxStar Sathi
    t_rox_dost = ConversationTurn(
        turn_id="t-rd",
        room_id="r-route",
        participant_identity="h-1",
        participant_display_name="User",
        transcript="RoxStar Dost, kya haal hai?",
        started_at=now,
        ended_at=now,
        is_complete=True,
    )
    assert router.route(t_rox_dost, e_yes).selected_bot == BotType.DOST

    t_rox_sathi = ConversationTurn(
        turn_id="t-rs",
        room_id="r-route",
        participant_identity="h-1",
        participant_display_name="User",
        transcript="RoxStar Sathi, help me.",
        started_at=now,
        ended_at=now,
        is_complete=True,
    )
    assert router.route(t_rox_sathi, e_yes).selected_bot == BotType.SATHI

    # 4. Unaddressed question -> Exactly ONE bot, stable fallback
    t_unaddressed = ConversationTurn(
        turn_id="t-un1",
        room_id="r-fallback",
        participant_identity="h-1",
        participant_display_name="User",
        transcript="What is the weather today?",
        started_at=now,
        ended_at=now,
        is_complete=True,
    )
    e_un = ResponseEligibility(
        should_respond=True,
        reason="explicit_question",
        confidence=0.9,
        trigger_type=TriggerType.DIRECT_QUESTION,
    )
    r_un1 = router.route(t_unaddressed, e_un)
    assert r_un1.selected_bot in (BotType.DOST, BotType.SATHI)
    assert r_un1.selected_bot != BotType.NONE
    assert r_un1.routing_source == "fallback"

    # Next unaddressed in same room alternates (round-robin)
    r_un2 = router.route(t_unaddressed, e_un)
    assert r_un2.selected_bot in (BotType.DOST, BotType.SATHI)
    assert r_un2.selected_bot != r_un1.selected_bot


# ============================================================================
# 5. CONTEXT & SPEAKER ISOLATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_speaker_separation_and_context_truncation():
    """Verify facts and turns are strictly separated by participant_identity."""
    context_mgr = ConversationContextManager(max_turns=3)
    room = "test-room-context"
    now = datetime.now(timezone.utc)

    # Rahul disclosures
    t_r1 = ConversationTurn(
        turn_id="t-r1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="My name is Rahul.",
        started_at=now,
        ended_at=now,
        is_complete=True,
    )
    await context_mgr.update_context_and_snapshot(t_r1)

    t_r2 = ConversationTurn(
        turn_id="t-r2",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="I like cricket.",
        started_at=now,
        ended_at=now,
        is_complete=True,
    )
    await context_mgr.update_context_and_snapshot(t_r2)

    # Priya disclosures
    t_p1 = ConversationTurn(
        turn_id="t-p1",
        room_id=room,
        participant_identity="human-priya",
        participant_display_name="Priya",
        transcript="My name is Priya.",
        started_at=now,
        ended_at=now,
        is_complete=True,
    )
    snap = await context_mgr.update_context_and_snapshot(t_p1)

    # Verify speaker separation
    assert "human-rahul" in snap.all_speaker_profiles
    assert "human-priya" in snap.all_speaker_profiles

    rahul_facts = snap.all_speaker_profiles["human-rahul"].facts
    priya_facts = snap.all_speaker_profiles["human-priya"].facts

    assert any("Cricket" in f for f in rahul_facts)
    assert not any("Cricket" in f for f in priya_facts)
    assert any("Priya" in f for f in priya_facts)
    assert not any("Priya" in f for f in rahul_facts)

    # Test FIFO context window truncation (max_turns=3)
    t_r3 = ConversationTurn(
        turn_id="t-r3",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="Another turn",
        started_at=now,
        ended_at=now,
        is_complete=True,
    )
    snap2 = await context_mgr.update_context_and_snapshot(t_r3)
    assert len(snap2.recent_turns) == 3
    assert snap2.recent_turns[0].turn_id == "t-r2"  # oldest t-r1 evicted


# ============================================================================
# 6. MULTI-USER FOLLOW-UP & CONTEXT ACCESS (Architectural Correction 1 & 7A)
# ============================================================================

@pytest.mark.asyncio
async def test_multi_user_follow_up_accesses_prior_context():
    """
    Rahul asks: 'AI kya hota hai?'
    Then Priya: 'Thoda aur simple batao.'
    Verify:
    - Context snapshot is updated BEFORE eligibility.
    - Priya's eligibility classifier accesses Rahul's preceding turn.
    - Classified as FOLLOW_UP.
    - Speaker attribution is preserved (Priya).
    - Exactly one bot selected.
    """
    orchestrator_svc = OrchestratorService()
    room = "test-multi-followup"

    # Step 1: Rahul asks
    evt_rahul = TranscriptEvent(
        event_id="evt-rahul-1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="AI kya hota hai?",
        status="final",
    )
    dec_rahul = await orchestrator_svc.handle_transcript_event(evt_rahul)
    assert dec_rahul is not None
    assert dec_rahul.eligibility.should_respond is True
    assert dec_rahul.routing.selected_bot in (BotType.DOST, BotType.SATHI)

    # Release lock so next turn can test acquisition
    await turn_lock_manager.release(room)

    # Step 2: Priya follow-up
    evt_priya = TranscriptEvent(
        event_id="evt-priya-1",
        room_id=room,
        participant_identity="human-priya",
        participant_display_name="Priya",
        transcript="Thoda aur simple batao.",
        status="final",
    )
    dec_priya = await orchestrator_svc.handle_transcript_event(evt_priya)
    assert dec_priya is not None
    assert dec_priya.eligibility.should_respond is True
    assert dec_priya.eligibility.trigger_type == TriggerType.FOLLOW_UP
    assert dec_priya.eligibility.reason == "contextual_follow_up"
    assert dec_priya.routing.selected_bot in (BotType.DOST, BotType.SATHI)


# ============================================================================
# 7. TURN LOCK MUTEX & ROOM ISOLATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_turn_lock_mutex_and_room_isolation():
    lock_mgr = TurnLockManager(default_ttl_seconds=10)
    room_a = "room-mutex-a"
    room_b = "room-mutex-b"

    # DOST acquires lock on Room A
    acquired = await lock_mgr.acquire(room_a, BotType.DOST, "turn-1")
    assert acquired is True
    assert await lock_mgr.is_locked(room_a) is True

    # SATHI attempts acquisition on Room A -> BLOCKED
    blocked = await lock_mgr.acquire(room_a, BotType.SATHI, "turn-2")
    assert blocked is False

    # Room B is isolated: SATHI CAN acquire on Room B
    acquired_b = await lock_mgr.acquire(room_b, BotType.SATHI, "turn-3")
    assert acquired_b is True

    # DOST releases lock on Room A
    released = await lock_mgr.release(room_a, BotType.DOST)
    assert released is True
    assert await lock_mgr.is_locked(room_a) is False

    # SATHI can now acquire on Room A
    acquired_after = await lock_mgr.acquire(room_a, BotType.SATHI, "turn-4")
    assert acquired_after is True


# ============================================================================
# 8. TEXT CHAT AUTHENTICATION & UNIFICATION TESTS (Correction 2 & 7C)
# ============================================================================

def test_text_chat_authentication_and_unification():
    client = TestClient(app)
    room = "room-auth-chat"
    speaker = "human-rahul"

    # 1. Unauthenticated request -> HTTP 401
    res_no_auth = client.post(
        "/api/v1/orchestration/text-chat",
        json={"room_name": room, "text": "AI kya hota hai?"}
    )
    assert res_no_auth.status_code == 401

    # 2. Invalid token -> HTTP 403
    res_bad_token = client.post(
        "/api/v1/orchestration/text-chat",
        headers={"Authorization": "Bearer bad.invalid.token"},
        json={"room_name": room, "text": "AI kya hota hai?"}
    )
    assert res_bad_token.status_code == 403

    # 3. Token room mismatch -> HTTP 403
    token_other_room = generate_stt_token("other-room", speaker, "Rahul")
    res_mismatch = client.post(
        "/api/v1/orchestration/text-chat",
        headers={"Authorization": f"Bearer {token_other_room}"},
        json={"room_name": room, "text": "AI kya hota hai?"}
    )
    assert res_mismatch.status_code == 403

    # 4. Valid authenticated text chat -> Success & identical orchestration contract
    valid_token = generate_stt_token(room, speaker, "Rahul")
    res_ok = client.post(
        "/api/v1/orchestration/text-chat",
        headers={"Authorization": f"Bearer {valid_token}"},
        json={"room_name": room, "text": "AI kya hota hai?"}
    )
    assert res_ok.status_code == 200
    data = res_ok.json()
    assert "decision_id" in data
    assert data["eligibility"]["should_respond"] is True
    assert data["routing"]["selected_bot"] in ("DOST", "SATHI")


# ============================================================================
# 9. 5 ASSIGNMENT SCENARIOS (Section 25)
# ============================================================================

@pytest.mark.asyncio
async def test_assignment_scenario_1_rahul_ai_question():
    """Scenario 1: Rahul 'AI kya hota hai?' -> final -> complete turn -> response required -> one bot."""
    svc = OrchestratorService()
    room = "assign-scenario-1"
    evt = TranscriptEvent(
        event_id="evt-sc1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="AI kya hota hai?",
        status="final",
    )
    dec = await svc.handle_transcript_event(evt)
    assert dec is not None
    assert dec.eligibility.should_respond is True
    assert dec.routing.selected_bot in (BotType.DOST, BotType.SATHI)


@pytest.mark.asyncio
async def test_assignment_scenario_2_rahul_cloud_computing():
    """Scenario 2: Rahul 'Can you explain cloud computing?' -> complete turn -> response required -> one bot."""
    svc = OrchestratorService()
    room = "assign-scenario-2"
    evt = TranscriptEvent(
        event_id="evt-sc2",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="Can you explain cloud computing?",
        status="final",
    )
    dec = await svc.handle_transcript_event(evt)
    assert dec is not None
    assert dec.eligibility.should_respond is True
    assert dec.routing.selected_bot in (BotType.DOST, BotType.SATHI)


@pytest.mark.asyncio
async def test_assignment_scenario_3_rahul_srk_followup():
    """Scenario 3: Rahul 'Shah Rukh Khan ke baare mein batao.' -> 'Unki koi famous movie batao.' -> FOLLOW_UP."""
    svc = OrchestratorService()
    room = "assign-scenario-3"

    evt1 = TranscriptEvent(
        event_id="evt-sc3-1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="Shah Rukh Khan ke baare mein batao.",
        status="final",
    )
    await svc.handle_transcript_event(evt1)
    await turn_lock_manager.release(room)

    evt2 = TranscriptEvent(
        event_id="evt-sc3-2",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="Unki koi famous movie batao.",
        status="final",
    )
    dec2 = await svc.handle_transcript_event(evt2)
    assert dec2 is not None
    assert dec2.eligibility.should_respond is True
    assert dec2.eligibility.trigger_type == TriggerType.FOLLOW_UP


@pytest.mark.asyncio
async def test_assignment_scenario_4_rahul_priya_multiuser_followup():
    """Scenario 4: Rahul 'AI kya hota hai?' -> Priya 'Thoda aur simple batao.' -> speaker attribution & context preserved."""
    svc = OrchestratorService()
    room = "assign-scenario-4"

    evt1 = TranscriptEvent(
        event_id="evt-sc4-1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="AI kya hota hai?",
        status="final",
    )
    await svc.handle_transcript_event(evt1)
    await turn_lock_manager.release(room)

    evt2 = TranscriptEvent(
        event_id="evt-sc4-2",
        room_id=room,
        participant_identity="human-priya",
        participant_display_name="Priya",
        transcript="Thoda aur simple batao.",
        status="final",
    )
    dec2 = await svc.handle_transcript_event(evt2)
    assert dec2 is not None
    assert dec2.eligibility.trigger_type == TriggerType.FOLLOW_UP
    assert dec2.routing.selected_bot in (BotType.DOST, BotType.SATHI)


@pytest.mark.asyncio
async def test_assignment_scenario_5_rahul_facts_retention():
    """Scenario 5: Rahul 'My name is Rahul.' / 'I like cricket.' -> context contains Rahul-specific turns/facts."""
    room = "assign-scenario-5"
    now = datetime.now(timezone.utc)
    context_mgr = ConversationContextManager()

    t1 = ConversationTurn(
        turn_id="t-f1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="My name is Rahul.",
        started_at=now,
        ended_at=now,
        is_complete=True,
    )
    await context_mgr.update_context_and_snapshot(t1)

    t2 = ConversationTurn(
        turn_id="t-f2",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="I like cricket.",
        started_at=now,
        ended_at=now,
        is_complete=True,
    )
    snap = await context_mgr.update_context_and_snapshot(t2)

    rahul_profile = snap.all_speaker_profiles.get("human-rahul")
    assert rahul_profile is not None
    assert any("Name: Rahul" in f for f in rahul_profile.facts)
    assert any("Cricket" in f for f in rahul_profile.facts)
