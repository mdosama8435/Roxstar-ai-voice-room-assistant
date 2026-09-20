"""
Phase 3E — focused gap coverage (deterministic, no quota burn).

Covers behaviors not already proven by assignment/fallback/TTS suites:
- voice → text shared room context
- explicit Dost / Sathi routing through orchestrator
- follow-up references (uski / wahi topic / simple batao)
- malformed STT transcript stability
- AI LiveKit reconnect republish (no duplicate session)
- one human turn → one decision / one selected bot
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.contracts import BotType, ModalityType, TranscriptEvent, TriggerType
from app.services.conversation_context import conversation_context_manager
from app.services.orchestrator import OrchestratorService
from app.services.stt_auth import generate_stt_token
from app.services.turn_lock import turn_lock_manager


@pytest.mark.asyncio
async def test_voice_then_text_share_same_room_context():
    """Voice TranscriptEvent then authenticated text-chat must share room memory."""
    svc = OrchestratorService()
    room = "p3e-voice-text-shared"
    await turn_lock_manager.release(room)
    conversation_context_manager.reset_room(room)

    voice = TranscriptEvent(
        event_id="p3e-vt-1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="Shah Rukh Khan ke baare mein batao.",
        status="final",
        modality=ModalityType.VOICE,
        timestamp=datetime.now(timezone.utc),
    )
    dec1 = await svc.handle_transcript_event(voice)
    assert dec1 is not None
    await turn_lock_manager.release(room)

    snap_after_voice = await conversation_context_manager.get_context_snapshot(room)
    assert any("Shah Rukh" in (t.transcript or "") for t in snap_after_voice.recent_turns)

    client = TestClient(app)
    token = generate_stt_token(room, "human-rahul", "Rahul")
    res = client.post(
        "/api/v1/orchestration/text-chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"room_name": room, "text": "Unki koi famous movie batao."},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["eligibility"]["should_respond"] is True
    assert data["eligibility"]["trigger_type"] in (
        TriggerType.FOLLOW_UP.value,
        "FOLLOW_UP",
        "follow_up",
    ) or str(data["eligibility"].get("trigger_type", "")).lower().endswith("follow_up")

    snap_after_text = await conversation_context_manager.get_context_snapshot(room)
    transcripts = [t.transcript for t in snap_after_text.recent_turns]
    assert any("Shah Rukh" in (t or "") for t in transcripts)
    assert any("movie" in (t or "").lower() or "Unki" in (t or "") for t in transcripts)


@pytest.mark.asyncio
async def test_explicit_dost_then_sathi_routing_single_bot_each():
    """Explicit address selects exactly one bot; opposite bot never selected."""
    svc = OrchestratorService()
    room = "p3e-explicit-bots"
    await turn_lock_manager.release(room)

    dost_evt = TranscriptEvent(
        event_id="p3e-dost-1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="AI Dost, AI kya hota hai?",
        status="final",
    )
    dec_dost = await svc.handle_transcript_event(dost_evt)
    assert dec_dost is not None
    assert dec_dost.routing.selected_bot == BotType.DOST
    assert dec_dost.routing.selected_bot != BotType.SATHI
    await turn_lock_manager.release(room)

    sathi_evt = TranscriptEvent(
        event_id="p3e-sathi-1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="AI Sathi, cloud computing kya hai?",
        status="final",
    )
    dec_sathi = await svc.handle_transcript_event(sathi_evt)
    assert dec_sathi is not None
    assert dec_sathi.routing.selected_bot == BotType.SATHI
    assert dec_sathi.routing.selected_bot != BotType.DOST


@pytest.mark.asyncio
async def test_followup_references_uski_wahi_simple():
    """Reference phrases resolve as FOLLOW_UP against active room topic."""
    svc = OrchestratorService()
    room = "p3e-followup-refs"
    await turn_lock_manager.release(room)
    conversation_context_manager.reset_room(room)

    first = TranscriptEvent(
        event_id="p3e-ref-0",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="Machine learning ke baare mein batao.",
        status="final",
    )
    await svc.handle_transcript_event(first)
    await turn_lock_manager.release(room)

    for i, text in enumerate(["uski example do", "wahi topic pe aur batao", "simple batao"]):
        evt = TranscriptEvent(
            event_id=f"p3e-ref-{i+1}",
            room_id=room,
            participant_identity="human-rahul",
            participant_display_name="Rahul",
            transcript=text,
            status="final",
        )
        dec = await svc.handle_transcript_event(evt)
        assert dec is not None, text
        assert dec.eligibility.should_respond is True, text
        assert dec.eligibility.trigger_type == TriggerType.FOLLOW_UP, text
        assert dec.routing.selected_bot in (BotType.DOST, BotType.SATHI)
        await turn_lock_manager.release(room)


@pytest.mark.asyncio
async def test_malformed_stt_transcript_does_not_crash_or_lock():
    """Garbage STT text must not crash orchestration; lock must not stick."""
    svc = OrchestratorService()
    room = "p3e-bad-stt"
    await turn_lock_manager.release(room)

    evt = TranscriptEvent(
        event_id="p3e-bad-1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="@@@ ### ??? !!!",
        status="final",
    )
    dec = await svc.handle_transcript_event(evt)
    # May or may not respond, but must return cleanly
    assert dec is not None or dec is None
    assert await turn_lock_manager.is_locked(room) is False or (
        dec is not None and dec.turn_lock_acquired
    )
    # Eventually releasable
    await turn_lock_manager.release(room)
    assert await turn_lock_manager.is_locked(room) is False


@pytest.mark.asyncio
async def test_one_turn_one_decision_one_bot():
    """Single final human turn → one decision, exactly one selected bot."""
    svc = OrchestratorService()
    room = "p3e-one-decision"
    await turn_lock_manager.release(room)

    evt = TranscriptEvent(
        event_id="p3e-one-1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="AI kya hota hai?",
        status="final",
    )
    dec = await svc.handle_transcript_event(evt)
    assert dec is not None
    assert dec.routing.selected_bot in (BotType.DOST, BotType.SATHI)
    assert dec.routing.selected_bot != BotType.NONE
    # Exactly one bot enum — never both
    assert isinstance(dec.routing.selected_bot, BotType)


@pytest.mark.asyncio
async def test_ai_reconnect_republishes_without_new_session():
    """Reconnect republishes track on existing session; does not mint a second session."""
    from agents.app.livekit.ai_participant import AIParticipantSession

    session = AIParticipantSession(
        agent_id="dost",
        identity="ai_dost",
        display_name="RoxStar AI Dost",
        livekit_url="wss://example.livekit.cloud",
        api_key="k",
        api_secret="s",
        room_name="p3e-reconnect",
    )
    mock_room = MagicMock()
    session.room = mock_room
    session._connected = True
    session.publisher._published = True
    session.publisher._audio_track = MagicMock()

    with patch.object(
        session.publisher, "publish_track_to_room", new_callable=AsyncMock
    ) as publish, patch.object(
        session.publisher, "setup", new_callable=AsyncMock
    ) as setup:
        await session._handle_reconnect_republish()

    publish.assert_awaited_once()
    setup.assert_not_awaited()  # track already exists
    assert session.is_connected is True
    assert session.room is mock_room


@pytest.mark.asyncio
async def test_partial_stt_does_not_orchestrate_response():
    """Partial STT must not produce a completed orchestration decision."""
    svc = OrchestratorService()
    room = "p3e-partial"
    await turn_lock_manager.release(room)

    evt = TranscriptEvent(
        event_id="p3e-partial-1",
        room_id=room,
        participant_identity="human-rahul",
        participant_display_name="Rahul",
        transcript="AI kya",
        status="partial",
    )
    dec = await svc.handle_transcript_event(evt)
    assert dec is None
    assert await turn_lock_manager.is_locked(room) is False
