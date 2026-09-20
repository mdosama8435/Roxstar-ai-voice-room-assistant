"""
Phase 3F.3.3 — barge-in polish + eligibility-aligned interruption.

Casual/ambient STT (short or long) must not cancel in-flight AI speech.
Meaningful questions/requests/bot address must still barge-in.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
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
from app.services.conversation_context import RoomContextSnapshot
from app.services.orchestrator import OrchestratorService
from app.services.response_eligibility import ResponseEligibilityService
from app.services.turn_lock import turn_lock_manager


def _turn(room: str, turn_id: str, text: str, *, identity="human-rahul", name="Rahul") -> ConversationTurn:
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


def _snapshot(room: str) -> RoomContextSnapshot:
    return RoomContextSnapshot(
        snapshot_id=f"snap-{room}",
        room_id=room,
        recent_turns=[],
        all_speaker_profiles={},
        current_topic=None,
        created_at=datetime.now(timezone.utc),
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


class TestLongCasualBargeInGate:
    def test_short_casual_instagram(self):
        assert OrchestratorService.should_barge_in_for_turn(_turn("r", "t1", "Instagram")) is False

    def test_longer_casual_english(self):
        text = "Yeah right just going home later after the match maybe"
        turn = _turn("r", "t2", text)
        elig = ResponseEligibilityService().evaluate(turn, None)
        assert elig.trigger_type == TriggerType.CASUAL_STATEMENT
        assert OrchestratorService.should_barge_in_for_turn(turn) is False

    def test_longer_casual_hindi_ambient(self):
        text = "ये जो बेटा है, फिर भी एक ना उछा वाला काम कर रहा है।"
        turn = _turn("r", "t3", text, identity="human-priya", name="Priya")
        elig = ResponseEligibilityService().evaluate(turn, None)
        assert elig.should_respond is False
        assert elig.trigger_type == TriggerType.CASUAL_STATEMENT
        assert OrchestratorService.should_barge_in_for_turn(turn) is False

    def test_meaningful_question_still_barges_in(self):
        assert OrchestratorService.should_barge_in_for_turn(_turn("r", "t4", "AI kya hota hai?")) is True

    def test_explicit_bot_address_still_barges_in(self):
        assert (
            OrchestratorService.should_barge_in_for_turn(
                _turn("r", "t5", "AI Sathi, tum batao.", identity="human-priya", name="Priya")
            )
            is True
        )

    def test_direct_request_still_barges_in(self):
        assert OrchestratorService.should_barge_in_for_turn(_turn("r", "t6", "thoda simple batao")) is True


@pytest.mark.asyncio
async def test_long_casual_does_not_cancel_inflight_tts_generation():
    """Longer casual STT during generation must not cancel the canonical response."""
    orch = OrchestratorService()
    room = "room-3f33-casual"
    turn_id = "turn-3f33-main"
    await turn_lock_manager.acquire(room, BotType.DOST, turn_id)

    class SlowLLM:
        def __init__(self):
            self.cancel_called = False

        async def stream(self, llm_request):
            yield MagicMock(text_delta="Haan bhai, ", sequence=0, is_final=False)
            await asyncio.sleep(0.2)
            yield MagicMock(text_delta="AI machine intelligence hai.", sequence=1, is_final=True)

        async def cancel(self, request_id):
            self.cancel_called = True

        def get_metadata(self, request_id):
            return {"final_provider": "mock"}

    llm = SlowLLM()
    orch._active_turn_by_room[room] = turn_id

    with patch("app.services.orchestrator.get_llm_provider", return_value=llm), patch(
        "app.services.orchestrator.OutputValidator.validate",
        return_value="Haan bhai, AI machine intelligence hai.",
    ), patch(
        "app.services.orchestrator.conversation_context_manager.add_turn",
        new_callable=AsyncMock,
    ), patch(
        "app.services.orchestrator.ConversationContextBuilder.build_request",
        return_value=MagicMock(request_id="llm-3f33-1"),
    ), patch.object(orch, "_broadcast_to_livekit_room", new_callable=AsyncMock):
        gen_task = asyncio.create_task(
            orch.generate_and_broadcast_ai_response(
                decision=_decision(room, turn_id, BotType.DOST),
                turn=_turn(room, turn_id, "AI kya hota hai?"),
                snapshot=_snapshot(room),
                turn_completed_perf=asyncio.get_event_loop().time(),
            )
        )
        await asyncio.sleep(0.05)

        ambient = _turn(
            room,
            "turn-ambient-long",
            "अली वाले घर जा रहे थे, राम सर के शादी से पूछो का कि भजवा दें।",
            identity="human-priya",
            name="Priya",
        )
        assert orch.should_barge_in_for_turn(ambient) is False
        if room in orch._active_turn_by_room and orch.should_barge_in_for_turn(ambient):
            await orch.interrupt_room_generation(room, reason="barge_in")

        result = await gen_task

    assert result is not None
    assert "AI" in result.text or "intelligence" in result.text or "bhai" in result.text.lower()
    assert llm.cancel_called is False
    turn_lock_manager.reset_room(room)
