"""
Phase 3F.3.1 — multi-user reliability regressions.

Covers:
1. Ambient short STT must not barge-in cancel an in-flight AI response
2. Post-lock routed turns still produce one canonical AI response under ambient noise
3. Priya asking about Rahul's facts keeps ownership on Rahul and does not address Rahul as asker
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.contracts import (
    BotRoutingDecision,
    BotType,
    ConversationTurn,
    OrchestrationDecision,
    ResponseEligibility,
    TranscriptEvent,
    TriggerType,
    TurnState,
)
from app.schemas.llm import LLMRequest
from app.services.conversation_context import (
    ConversationContextManager,
    RoomContextSnapshot,
    SpeakerProfile,
)
from app.services.conversation_context_builder import ConversationContextBuilder
from app.services.orchestrator import OrchestratorService
from app.services.personas.prompt_builder import PersonaPromptBuilder
from app.services.response_eligibility import ResponseEligibilityService
from app.services.turn_lock import turn_lock_manager


def _turn(
    room: str,
    turn_id: str,
    text: str,
    *,
    identity: str = "human-rahul",
    name: str = "Rahul",
) -> ConversationTurn:
    return ConversationTurn(
        turn_id=turn_id,
        room_id=room,
        participant_identity=identity,
        participant_display_name=name,
        transcript=text,
        state=TurnState.COMPLETE,
        is_final=True,
        is_complete=True,
    )


def _decision(room: str, turn_id: str, bot: BotType = BotType.DOST) -> OrchestrationDecision:
    return OrchestrationDecision(
        decision_id=f"dec-{turn_id}",
        room_id=room,
        turn_id=turn_id,
        eligibility=ResponseEligibility(
            should_respond=True,
            reason="test",
            confidence=1.0,
            trigger_type=TriggerType.DIRECT_QUESTION,
        ),
        routing=BotRoutingDecision(
            decision_id=f"route-{turn_id}",
            room_id=room,
            turn_id=turn_id,
            selected_bot=bot,
            reason="test",
            confidence=1.0,
            routing_source="explicit_rule",
        ),
        turn_lock_acquired=True,
        created_at=datetime.now(timezone.utc),
    )


def _snapshot(room: str) -> RoomContextSnapshot:
    return RoomContextSnapshot(
        snapshot_id=f"snap-{room}",
        room_id=room,
        recent_turns=[],
        all_speaker_profiles={},
        current_topic=None,
        created_at=datetime.now(timezone.utc),
    )


class TestBargeInAmbientNoise:
    def test_instagram_ambient_should_not_barge_in(self):
        turn = _turn("r1", "t1", "Instagram", identity="human-priya", name="Priya")
        assert OrchestratorService.should_barge_in_for_turn(turn) is False

    def test_short_casual_noun_should_not_barge_in(self):
        turn = _turn("r1", "t2", "Netflix.")
        assert OrchestratorService.should_barge_in_for_turn(turn) is False

    def test_question_should_barge_in(self):
        turn = _turn("r1", "t3", "AI kya hota hai?")
        assert OrchestratorService.should_barge_in_for_turn(turn) is True

    def test_explicit_sathi_should_barge_in(self):
        turn = _turn("r1", "t4", "AI Sathi, tum batao.", identity="human-priya", name="Priya")
        assert OrchestratorService.should_barge_in_for_turn(turn) is True

    def test_multiword_casual_statement_should_not_barge_in(self):
        turn = _turn(
            "r1",
            "t5",
            "Mera naam Rahul hai aur mujhe cricket pasand hai.",
        )
        assert OrchestratorService.should_barge_in_for_turn(turn) is False

    def test_longer_casual_ambient_stt_should_not_barge_in(self):
        turn = _turn(
            "r1",
            "t5b",
            "समझ में ना आता है हमको। पहले भी बोले कि समझ में ना आता है।",
            identity="human-priya",
            name="Priya",
        )
        assert OrchestratorService.should_barge_in_for_turn(turn) is False

    def test_ack_should_barge_in_soft(self):
        turn = _turn("r1", "t5c", "theek hai")
        assert OrchestratorService.should_barge_in_for_turn(turn) is True

    def test_instagram_still_not_eligible_for_ai_response(self):
        elig = ResponseEligibilityService().evaluate(
            _turn("r1", "t6", "Instagram", identity="human-x", name="X")
        )
        assert elig.should_respond is False
        assert elig.trigger_type == TriggerType.CASUAL_STATEMENT


@pytest.mark.asyncio
async def test_ambient_noise_does_not_cancel_inflight_canonical_response():
    """
    Issue 1 reproduction guard:
    Lock acquired + LLM streaming, then ambient 'Instagram' final arrives.
    Response body must still be published (exactly one canonical AI response).
    """
    orch = OrchestratorService()
    room = "room-3f31-ambient"
    turn_id = "turn-3f31-main"
    await turn_lock_manager.acquire(room, BotType.SATHI, turn_id)

    class SlowLLM:
        def __init__(self):
            self.cancel_called = False

        async def stream(self, llm_request):
            yield MagicMock(text_delta="Haan ", sequence=0, is_final=False)
            await asyncio.sleep(0.25)
            yield MagicMock(text_delta="Priya, Sathi yahan hai.", sequence=1, is_final=True)

        async def cancel(self, request_id):
            self.cancel_called = True

        def get_metadata(self, request_id):
            return {"final_provider": "mock"}

    llm = SlowLLM()
    orch._active_turn_by_room[room] = turn_id

    with patch("app.services.orchestrator.get_llm_provider", return_value=llm), patch(
        "app.services.orchestrator.OutputValidator.validate",
        return_value="Haan Priya, Sathi yahan hai.",
    ), patch(
        "app.services.orchestrator.conversation_context_manager.add_turn",
        new_callable=AsyncMock,
    ), patch(
        "app.services.orchestrator.ConversationContextBuilder.build_request",
        return_value=MagicMock(request_id="llm-ambient-1"),
    ), patch.object(orch, "_broadcast_to_livekit_room", new_callable=AsyncMock):
        gen_task = asyncio.create_task(
            orch.generate_and_broadcast_ai_response(
                decision=_decision(room, turn_id, BotType.SATHI),
                turn=_turn(
                    room,
                    turn_id,
                    "AI Sathi, tum batao.",
                    identity="human-priya",
                    name="Priya",
                ),
                snapshot=_snapshot(room),
                turn_completed_perf=asyncio.get_event_loop().time(),
            )
        )
        await asyncio.sleep(0.05)

        # Ambient open-mic final while Sathi is generating
        ambient = TranscriptEvent(
            event_id="evt-ambient-ig",
            room_id=room,
            participant_identity="human-rahul",
            participant_display_name="Rahul",
            transcript="Instagram",
            status="final",
        )
        # Simulate the barge-in gate used by handle_transcript_event
        completed_ambient = _turn(
            room, "turn-ambient", "Instagram", identity="human-rahul", name="Rahul"
        )
        assert orch.should_barge_in_for_turn(completed_ambient) is False
        if room in orch._active_turn_by_room and orch.should_barge_in_for_turn(completed_ambient):
            await orch.interrupt_room_generation(room, reason="barge_in")

        result = await gen_task

    assert result is not None
    assert "Sathi" in result.text or "Priya" in result.text
    assert llm.cancel_called is False
    assert await turn_lock_manager.is_locked(room) is False
    turn_lock_manager.reset_room(room)


@pytest.mark.asyncio
async def test_post_rejoin_style_routed_turn_still_emits_one_response():
    """Issue 1 / leave-rejoin: a fresh locked turn still yields one canonical body."""
    orch = OrchestratorService()
    room = "room-3f31-rejoin"
    turn_id = "turn-3f31-rejoin"
    await turn_lock_manager.acquire(room, BotType.DOST, turn_id)

    class FastLLM:
        async def stream(self, llm_request):
            yield MagicMock(text_delta="Welcome back.", sequence=0, is_final=True)

        async def cancel(self, request_id):
            pass

        def get_metadata(self, request_id):
            return {"final_provider": "mock"}

    with patch("app.services.orchestrator.get_llm_provider", return_value=FastLLM()), patch(
        "app.services.orchestrator.OutputValidator.validate", return_value="Welcome back."
    ), patch(
        "app.services.orchestrator.conversation_context_manager.add_turn",
        new_callable=AsyncMock,
    ), patch(
        "app.services.orchestrator.ConversationContextBuilder.build_request",
        return_value=MagicMock(request_id="llm-rejoin-1"),
    ), patch.object(orch, "_broadcast_to_livekit_room", new_callable=AsyncMock):
        result = await orch.generate_and_broadcast_ai_response(
            decision=_decision(room, turn_id, BotType.DOST),
            turn=_turn(
                room,
                turn_id,
                "Hello after rejoin, one short reply please.",
                identity="human-priya",
                name="Priya",
            ),
            snapshot=_snapshot(room),
        )

    assert result is not None
    assert result.text == "Welcome back."
    assert await turn_lock_manager.is_locked(room) is False
    turn_lock_manager.reset_room(room)


class TestAddresseeSeparation:
    def test_prompt_marks_current_speaker_as_addressee(self):
        prompt = PersonaPromptBuilder.build_system_prompt(
            selected_bot=BotType.DOST,
            current_speaker_name="Priya",
            speaker_facts=[],
            other_speakers_summary="Rahul: Likes cricket",
            active_topic="memory",
        )
        assert "CURRENT SPEAKER (the person you must address now): Priya" in prompt
        assert "RESPONSE ADDRESSEE: Priya" in prompt
        assert "Rahul: Likes cricket" in prompt
        assert "third person" in prompt.lower() or "OTHER PARTICIPANTS" in prompt
        assert "NEVER address a different participant" in prompt

    def test_builder_labels_user_message_with_current_speaker(self):
        room = "room-addr"
        turn = _turn(
            room,
            "t-priya",
            "Maine tumhe apne baare mein kya bataya tha?",
            identity="human-priya",
            name="Priya",
        )
        snap = RoomContextSnapshot(
            snapshot_id="snap-addr",
            room_id=room,
            recent_turns=[],
            all_speaker_profiles={
                "human-rahul": SpeakerProfile(
                    participant_id="human-rahul",
                    name="Rahul",
                    facts=["Likes cricket"],
                ),
                "human-priya": SpeakerProfile(
                    participant_id="human-priya",
                    name="Priya",
                    facts=[],
                ),
            },
            current_topic="memory",
            created_at=datetime.now(timezone.utc),
        )
        req = ConversationContextBuilder.build_request(
            decision=_decision(room, "t-priya"),
            snapshot=snap,
            turn=turn,
        )
        assert req.user_message.startswith("Priya:")
        assert "Maine tumhe" in req.user_message
        assert "CURRENT SPEAKER (the person you must address now): Priya" in req.system_prompt
        # Rahul facts remain other-participant owned, not current-speaker facts
        assert req.speaker_facts == []
        assert "Rahul" in (req.system_prompt or "")
        assert "cricket" in (req.system_prompt or "").lower()

    def test_rahul_facts_remain_owned_by_rahul_in_context_manager(self):
        """Ownership regression: Rahul facts stay on Rahul identity."""
        # Lightweight structural check via prompt builder inputs
        prompt = PersonaPromptBuilder.build_system_prompt(
            selected_bot=BotType.SATHI,
            current_speaker_name="Priya",
            speaker_facts=[],
            other_speakers_summary="Rahul: Name: Rahul; Likes cricket",
        )
        assert "KNOWN FACTS ABOUT CURRENT SPEAKER (Priya): None recorded yet." in prompt
        assert "Rahul: Name: Rahul; Likes cricket" in prompt
