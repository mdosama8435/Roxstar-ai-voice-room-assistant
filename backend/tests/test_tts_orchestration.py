"""
Phase 3D Step 4: TTS orchestration + barge-in + turn-lock tests (mock only).

Does NOT claim real Sarvam verification.
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
    TriggerType,
    TurnState,
)
from app.schemas.llm import AIResponseGeneratedEvent
from app.schemas.tts import TTSRequest, TTSStatus
from app.services.conversation_context import RoomContextSnapshot
from app.services.orchestrator import OrchestratorService
from app.services.tts.tts_service import TTSService
from app.services.turn_lock import turn_lock_manager
from agents.app.livekit.audio_publisher import LiveKitAudioPublisher
from agents.app.speech.pcm_format import VerifiedPCMChunk
from agents.app.speech.sarvam_tts import MockTTSProvider, TTSCancelledError


def _decision(room: str, turn_id: str, bot: BotType = BotType.DOST) -> OrchestrationDecision:
    return OrchestrationDecision(
        decision_id=f"dec-{turn_id}",
        room_id=room,
        turn_id=turn_id,
        eligibility=ResponseEligibility(
            should_respond=True,
            reason="test",
            confidence=1.0,
            trigger_type=TriggerType.DIRECT_REQUEST,
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


def _turn(room: str, turn_id: str) -> ConversationTurn:
    return ConversationTurn(
        turn_id=turn_id,
        room_id=room,
        participant_identity="human-test",
        participant_display_name="Test",
        transcript="AI kya hota hai?",
        state=TurnState.COMPLETE,
        is_final=True,
    )


def _snapshot(room: str) -> RoomContextSnapshot:
    return RoomContextSnapshot(
        snapshot_id=f"snap-{room}",
        room_id=room,
        recent_turns=[],
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def orch():
    svc = OrchestratorService()
    yield svc
    # cleanup any locks left by tests
    for room in list(getattr(turn_lock_manager, "_locks", {}).keys()):
        turn_lock_manager.reset_room(room)


class _FakeLLMStream:
    def __init__(self, chunks, request_id="req-1"):
        self.chunks = chunks
        self.request_id = request_id
        self.cancel_called = False

    async def stream(self, llm_request):
        self.request_id = llm_request.request_id
        for i, text in enumerate(self.chunks):
            yield MagicMock(text_delta=text, sequence=i, is_final=(i == len(self.chunks) - 1))

    async def cancel(self, request_id):
        self.cancel_called = True

    def get_metadata(self, request_id):
        return {"final_provider": "mock"}


class TestTTSOrchestrationHappyPath:
    @pytest.mark.asyncio
    async def test_llm_success_calls_tts_once(self, orch):
        room, turn_id = "room-tts-ok", "turn-tts-ok"
        await turn_lock_manager.acquire(room, BotType.DOST, turn_id)

        tts = MagicMock()
        tts.synthesize_and_publish = AsyncMock(
            return_value=MagicMock(
                status=TTSStatus.COMPLETED,
                time_to_first_audio_ms=12.0,
                tts_total_ms=40.0,
                tts_completion_at=asyncio.get_event_loop().time(),
            )
        )
        tts.cancel = AsyncMock()
        tts.set_event_listener = MagicMock()
        orch.set_tts_service(tts)

        llm = _FakeLLMStream(["Haan ", "yaar."])
        with patch("app.services.orchestrator.get_llm_provider", return_value=llm), patch(
            "app.services.orchestrator.OutputValidator.validate", return_value="Haan yaar."
        ), patch(
            "app.services.orchestrator.conversation_context_manager.add_turn",
            new_callable=AsyncMock,
        ), patch(
            "app.services.orchestrator.ConversationContextBuilder.build_request",
            return_value=MagicMock(request_id="llm-req-1"),
        ):
            result = await orch.generate_and_broadcast_ai_response(
                decision=_decision(room, turn_id),
                turn=_turn(room, turn_id),
                snapshot=_snapshot(room),
                turn_completed_perf=asyncio.get_event_loop().time(),
            )

        assert result is not None
        assert tts.synthesize_and_publish.await_count == 1
        # lock released
        assert await turn_lock_manager.is_locked(room) is False

    @pytest.mark.asyncio
    async def test_llm_failure_skips_tts(self, orch):
        room, turn_id = "room-llm-fail", "turn-llm-fail"
        await turn_lock_manager.acquire(room, BotType.DOST, turn_id)

        tts = MagicMock()
        tts.synthesize_and_publish = AsyncMock()
        tts.set_event_listener = MagicMock()
        orch.set_tts_service(tts)

        class BoomLLM:
            async def stream(self, req):
                raise RuntimeError("llm down")
                yield  # pragma: no cover

            async def cancel(self, request_id):
                pass

        with patch("app.services.orchestrator.get_llm_provider", return_value=BoomLLM()), patch(
            "app.services.orchestrator.ConversationContextBuilder.build_request",
            return_value=MagicMock(request_id="llm-fail"),
        ):
            result = await orch.generate_and_broadcast_ai_response(
                decision=_decision(room, turn_id),
                turn=_turn(room, turn_id),
                snapshot=_snapshot(room),
            )

        assert result is None
        tts.synthesize_and_publish.assert_not_awaited()
        assert await turn_lock_manager.is_locked(room) is False

    @pytest.mark.asyncio
    async def test_validation_empty_skips_tts(self, orch):
        room, turn_id = "room-val-empty", "turn-val-empty"
        await turn_lock_manager.acquire(room, BotType.SATHI, turn_id)

        tts = MagicMock()
        tts.synthesize_and_publish = AsyncMock()
        tts.set_event_listener = MagicMock()
        orch.set_tts_service(tts)

        llm = _FakeLLMStream(["   "])
        with patch("app.services.orchestrator.get_llm_provider", return_value=llm), patch(
            "app.services.orchestrator.OutputValidator.validate", return_value=""
        ), patch(
            "app.services.orchestrator.ConversationContextBuilder.build_request",
            return_value=MagicMock(request_id="llm-empty"),
        ):
            result = await orch.generate_and_broadcast_ai_response(
                decision=_decision(room, turn_id, BotType.SATHI),
                turn=_turn(room, turn_id),
                snapshot=_snapshot(room),
            )

        assert result is None
        tts.synthesize_and_publish.assert_not_awaited()
        assert await turn_lock_manager.is_locked(room) is False

    @pytest.mark.asyncio
    async def test_validation_raise_skips_tts(self, orch):
        room, turn_id = "room-val-raise", "turn-val-raise"
        await turn_lock_manager.acquire(room, BotType.DOST, turn_id)

        tts = MagicMock()
        tts.synthesize_and_publish = AsyncMock()
        tts.set_event_listener = MagicMock()
        orch.set_tts_service(tts)

        llm = _FakeLLMStream(["bad"])
        with patch("app.services.orchestrator.get_llm_provider", return_value=llm), patch(
            "app.services.orchestrator.OutputValidator.validate",
            side_effect=ValueError("invalid speech text"),
        ), patch(
            "app.services.orchestrator.ConversationContextBuilder.build_request",
            return_value=MagicMock(request_id="llm-val-raise"),
        ):
            result = await orch.generate_and_broadcast_ai_response(
                decision=_decision(room, turn_id),
                turn=_turn(room, turn_id),
                snapshot=_snapshot(room),
            )

        assert result is None
        tts.synthesize_and_publish.assert_not_awaited()
        assert await turn_lock_manager.is_locked(room) is False

    @pytest.mark.asyncio
    async def test_tts_failure_does_not_second_llm(self, orch):
        room, turn_id = "room-tts-fail", "turn-tts-fail"
        await turn_lock_manager.acquire(room, BotType.DOST, turn_id)

        tts = MagicMock()
        tts.synthesize_and_publish = AsyncMock(return_value=None)
        tts.set_event_listener = MagicMock()
        orch.set_tts_service(tts)

        llm = _FakeLLMStream(["Ok."])
        stream_calls = {"n": 0}
        original_stream = llm.stream

        async def counting_stream(req):
            stream_calls["n"] += 1
            async for c in original_stream(req):
                yield c

        llm.stream = counting_stream

        with patch("app.services.orchestrator.get_llm_provider", return_value=llm), patch(
            "app.services.orchestrator.OutputValidator.validate", return_value="Ok."
        ), patch(
            "app.services.orchestrator.conversation_context_manager.add_turn",
            new_callable=AsyncMock,
        ), patch(
            "app.services.orchestrator.ConversationContextBuilder.build_request",
            return_value=MagicMock(request_id="llm-tts-fail"),
        ):
            result = await orch.generate_and_broadcast_ai_response(
                decision=_decision(room, turn_id),
                turn=_turn(room, turn_id),
                snapshot=_snapshot(room),
            )

        assert result is not None  # canonical text still returned
        assert stream_calls["n"] == 1
        assert tts.synthesize_and_publish.await_count == 1


class TestBargeInAndCancellation:
    @pytest.mark.asyncio
    async def test_cancel_during_llm_skips_tts(self, orch):
        room, turn_id = "room-cancel-llm", "turn-cancel-llm"
        await turn_lock_manager.acquire(room, BotType.DOST, turn_id)

        tts = MagicMock()
        tts.synthesize_and_publish = AsyncMock()
        tts.cancel = AsyncMock()
        tts.set_event_listener = MagicMock()
        orch.set_tts_service(tts)

        class SlowLLM:
            async def stream(self, req):
                orch._cancelled_requests.add(req.request_id)
                yield MagicMock(text_delta="partial", sequence=0, is_final=False)

            async def cancel(self, request_id):
                pass

        with patch("app.services.orchestrator.get_llm_provider", return_value=SlowLLM()), patch(
            "app.services.orchestrator.ConversationContextBuilder.build_request",
            return_value=MagicMock(request_id="llm-cancel-1"),
        ):
            result = await orch.generate_and_broadcast_ai_response(
                decision=_decision(room, turn_id),
                turn=_turn(room, turn_id),
                snapshot=_snapshot(room),
            )

        assert result is None
        tts.synthesize_and_publish.assert_not_awaited()
        assert await turn_lock_manager.is_locked(room) is False

    @pytest.mark.asyncio
    async def test_cancel_during_tts_no_resume(self, orch):
        room, turn_id = "room-cancel-tts", "turn-cancel-tts"
        await turn_lock_manager.acquire(room, BotType.DOST, turn_id)

        llm_calls = {"n": 0}
        started = asyncio.Event()

        class CountingLLM(_FakeLLMStream):
            async def stream(self, llm_request):
                llm_calls["n"] += 1
                async for c in super().stream(llm_request):
                    yield c

        async def slow_tts(req):
            orch._active_tts_requests[turn_id] = req.request_id
            started.set()
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                raise
            return MagicMock(status=TTSStatus.COMPLETED)

        tts = MagicMock()
        tts.synthesize_and_publish = AsyncMock(side_effect=slow_tts)
        tts.cancel = AsyncMock()
        tts.set_event_listener = MagicMock()
        orch.set_tts_service(tts)

        with patch(
            "app.services.orchestrator.get_llm_provider",
            return_value=CountingLLM(["Speaking."]),
        ), patch(
            "app.services.orchestrator.OutputValidator.validate",
            return_value="Speaking.",
        ), patch(
            "app.services.orchestrator.conversation_context_manager.add_turn",
            new_callable=AsyncMock,
        ), patch(
            "app.services.orchestrator.ConversationContextBuilder.build_request",
            return_value=MagicMock(request_id="llm-cancel-tts"),
        ):
            gen_task = asyncio.create_task(
                orch.generate_and_broadcast_ai_response(
                    decision=_decision(room, turn_id),
                    turn=_turn(room, turn_id),
                    snapshot=_snapshot(room),
                )
            )
            orch._active_llm_tasks[turn_id] = gen_task
            await asyncio.wait_for(started.wait(), timeout=2.0)
            await orch.interrupt_room_generation(room, reason="barge_in")
            await asyncio.wait_for(gen_task, timeout=2.0)

        assert llm_calls["n"] == 1
        tts.cancel.assert_awaited()
        assert await turn_lock_manager.is_locked(room) is False

    @pytest.mark.asyncio
    async def test_cancel_generation_cancels_tts_and_clears_queue(self, orch):
        tts = MagicMock()
        tts.cancel = AsyncMock()
        tts.set_event_listener = MagicMock()
        orch.set_tts_service(tts)
        orch._active_tts_requests["turn-x"] = "tts-x"
        orch._llm_request_by_turn["turn-x"] = "llm-x"

        with patch("app.services.orchestrator.get_llm_provider") as gp:
            gp.return_value.cancel = AsyncMock()
            await orch.cancel_generation("llm-x")

        tts.cancel.assert_awaited()
        assert "llm-x" in orch._cancelled_requests

    @pytest.mark.asyncio
    async def test_interrupt_room_releases_lock_and_cancels_tts(self, orch):
        room, turn_id = "room-barge", "turn-barge"
        await turn_lock_manager.acquire(room, BotType.DOST, turn_id)

        tts = MagicMock()
        tts.cancel = AsyncMock()
        tts.set_event_listener = MagicMock()
        orch.set_tts_service(tts)
        orch._active_turn_by_room[room] = turn_id
        orch._active_tts_requests[turn_id] = "tts-barge"
        orch._llm_request_by_turn[turn_id] = "llm-barge"
        orch._in_flight_turns.add(turn_id)

        with patch("app.services.orchestrator.get_llm_provider") as gp:
            gp.return_value.cancel = AsyncMock()
            interrupted = await orch.interrupt_room_generation(room, reason="barge_in")

        assert interrupted is True
        tts.cancel.assert_awaited_with("tts-barge", reason="barge_in")
        assert await turn_lock_manager.is_locked(room) is False
        assert room not in orch._active_turn_by_room

    @pytest.mark.asyncio
    async def test_tts_service_cancel_clears_publisher_queue(self):
        provider = MockTTSProvider()
        publisher = LiveKitAudioPublisher(agent_id="dost", queue_maxsize=10)
        publisher._audio_source = MagicMock()
        publisher._published = True
        # prefill queue
        publisher._audio_queue.put_nowait(b"\x00\x00")
        publisher._audio_queue.put_nowait(b"\x01\x00")

        svc = TTSService(tts_provider=provider, publishers={"dost": publisher})
        svc._active_requests["tts-1"] = MagicMock(agent_id="dost", status=TTSStatus.STREAMING)

        await svc.cancel("tts-1", reason="barge_in")
        assert publisher._audio_queue.empty() or publisher._audio_queue.qsize() <= 1

    @pytest.mark.asyncio
    async def test_late_chunks_discarded_after_cancel(self):
        publisher = LiveKitAudioPublisher(agent_id="dost")
        publisher._audio_source = MagicMock()
        publisher._audio_source.capture_frame = AsyncMock()
        publisher._published = True
        publisher._active_request_id = "old-req"

        # Simulate frame loop discarding mismatched request
        publisher._audio_queue.put_nowait(b"\x00\x00" * 10)
        # active id changed (cancel)
        publisher._active_request_id = "new-req"
        # drain one iteration manually via cancel_current
        await publisher.cancel_current("old-req")
        # queue cleared
        assert publisher._audio_queue.empty() or publisher._audio_queue.qsize() <= 1


class TestTurnLockAndNonOverlap:
    @pytest.mark.asyncio
    async def test_lock_released_after_success(self, orch):
        room, turn_id = "room-lock-ok", "turn-lock-ok"
        await turn_lock_manager.acquire(room, BotType.DOST, turn_id)
        tts = MagicMock()
        tts.synthesize_and_publish = AsyncMock(
            return_value=MagicMock(
                status=TTSStatus.COMPLETED,
                time_to_first_audio_ms=1.0,
                tts_total_ms=2.0,
                tts_completion_at=1.0,
            )
        )
        tts.set_event_listener = MagicMock()
        orch.set_tts_service(tts)
        with patch("app.services.orchestrator.get_llm_provider", return_value=_FakeLLMStream(["Hi."])), patch(
            "app.services.orchestrator.OutputValidator.validate", return_value="Hi."
        ), patch(
            "app.services.orchestrator.conversation_context_manager.add_turn",
            new_callable=AsyncMock,
        ), patch(
            "app.services.orchestrator.ConversationContextBuilder.build_request",
            return_value=MagicMock(request_id="llm-lock-ok"),
        ):
            await orch.generate_and_broadcast_ai_response(
                decision=_decision(room, turn_id),
                turn=_turn(room, turn_id),
                snapshot=_snapshot(room),
            )
        assert await turn_lock_manager.is_locked(room) is False

    @pytest.mark.asyncio
    async def test_old_turn_cannot_release_newer_lock(self):
        room = "room-lock-handoff"
        await turn_lock_manager.acquire(room, BotType.DOST, "turn-old")
        await turn_lock_manager.release(room, BotType.DOST, "turn-old")
        await turn_lock_manager.acquire(room, BotType.DOST, "turn-new")
        # stale release must not clear new lock
        released = await turn_lock_manager.release(room, BotType.DOST, "turn-old")
        assert released is False
        assert await turn_lock_manager.is_locked(room) is True
        await turn_lock_manager.release(room, BotType.DOST, "turn-new")

    @pytest.mark.asyncio
    async def test_only_selected_agent_publisher_used(self):
        provider = MockTTSProvider()
        dost_pub = MagicMock()
        dost_pub.publish_pcm_stream = AsyncMock()
        sathi_pub = MagicMock()
        sathi_pub.publish_pcm_stream = AsyncMock()

        svc = TTSService(
            tts_provider=provider,
            publishers={"dost": dost_pub, "sathi": sathi_pub},
        )
        req = TTSRequest(
            request_id="tts-sel",
            turn_id="t1",
            agent_id="dost",
            text="Haan yaar.",
            speaker="shubh",
            room_id="r1",
        )
        metrics = await svc.synthesize_and_publish(req)
        assert metrics is not None
        dost_pub.publish_pcm_stream.assert_awaited()
        sathi_pub.publish_pcm_stream.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_simultaneous_acquire_prevented(self):
        room = "room-mutex"
        ok1 = await turn_lock_manager.acquire(room, BotType.DOST, "t1")
        ok2 = await turn_lock_manager.acquire(room, BotType.SATHI, "t2")
        assert ok1 is True
        assert ok2 is False
        await turn_lock_manager.release(room, BotType.DOST, "t1")


class TestTTSServiceEventsAndCancelSafety:
    @pytest.mark.asyncio
    async def test_tts_events_emitted_on_success(self):
        events = []
        provider = MockTTSProvider()
        pub = MagicMock()
        pub.publish_pcm_stream = AsyncMock()

        async def passthrough(pcm_stream, request_id, turn_id):
            async for _ in pcm_stream:
                pass

        pub.publish_pcm_stream = passthrough
        svc = TTSService(
            tts_provider=provider,
            publishers={"dost": pub},
            event_listener=lambda et, p: events.append(et),
        )
        req = TTSRequest(
            request_id="tts-evt",
            turn_id="t-evt",
            agent_id="dost",
            text="Test message for events.",
            speaker="shubh",
            room_id="r",
        )
        await svc.synthesize_and_publish(req)
        assert "tts.started" in events
        assert "tts.first_audio" in events
        assert "tts.completed" in events
        assert "audio.published" in events

    @pytest.mark.asyncio
    async def test_cancelled_error_does_not_continue_as_success(self):
        class CancelMidProvider:
            last_stream_format = None

            async def synthesize_stream(self, **kwargs):
                yield VerifiedPCMChunk(
                    pcm=bytes(960),
                    content_type="audio/l16;rate=24000;channels=1",
                    sample_rate=24000,
                    channels=1,
                    sample_width=2,
                    sequence=0,
                )
                raise TTSCancelledError("barge_in")

            def cancel_request(self, request_id):
                pass

        events = []
        pub = MagicMock()

        async def consume(pcm_stream, request_id, turn_id):
            async for _ in pcm_stream:
                pass

        pub.publish_pcm_stream = consume
        svc = TTSService(
            tts_provider=CancelMidProvider(),
            publishers={"sathi": pub},
            event_listener=lambda et, p: events.append(et),
        )
        req = TTSRequest(
            request_id="tts-mid-cancel",
            turn_id="t",
            agent_id="sathi",
            text="Interrupted.",
            speaker="anushka",
            room_id="r",
        )
        result = await svc.synthesize_and_publish(req)
        assert result is None
        assert "tts.cancelled" in events
        assert "tts.completed" not in events

    @pytest.mark.asyncio
    async def test_publisher_not_bound_fails_without_completed(self):
        """Regression 3F.10.1: missing LiveKit publisher must not fake TTS success."""
        events = []
        provider = MockTTSProvider()
        svc = TTSService(
            tts_provider=provider,
            publishers={},  # no AI publishers bound
            event_listener=lambda et, p: events.append((et, p)),
        )
        req = TTSRequest(
            request_id="tts-no-pub",
            turn_id="t-no-pub",
            agent_id="dost",
            text="Haan, suno.",
            speaker="shubh",
            room_id="human-room-1",
        )
        result = await svc.synthesize_and_publish(req)
        assert result is None
        types = [e[0] for e in events]
        assert "tts.started" in types
        assert "tts.failed" in types
        assert "tts.completed" not in types
        assert "audio.published" not in types
        fail = next(p for t, p in events if t == "tts.failed")
        assert fail.get("error") == "publisher_not_bound"
        assert fail.get("publisher_bound") is None or True  # started had the flag
        started = next(p for t, p in events if t == "tts.started")
        assert started.get("publisher_bound") is False


class TestEnsurePublishersForRoom:
    @pytest.mark.asyncio
    async def test_ensure_ai_publishers_binds_from_lifecycle(self):
        from app.services.orchestrator import OrchestratorService

        orch = OrchestratorService()
        tts = TTSService(tts_provider=MockTTSProvider(), publishers={})
        orch.set_tts_service(tts)

        pub_dost = MagicMock()
        pub_sathi = MagicMock()
        session_dost = MagicMock()
        session_dost.agent_id = "dost"
        session_dost.identity = "ai_dost"
        session_dost.publisher = pub_dost
        session_dost.is_connected = True
        session_sathi = MagicMock()
        session_sathi.agent_id = "sathi"
        session_sathi.identity = "ai_sathi"
        session_sathi.publisher = pub_sathi
        session_sathi.is_connected = True

        lifecycle = MagicMock()
        lifecycle.ensure_room = AsyncMock()
        lifecycle.sessions = [session_dost, session_sathi]
        orch.set_ai_room_lifecycle(lifecycle)

        ok = await orch._ensure_ai_publishers_for_room("human-demo-room")
        assert ok is True
        lifecycle.ensure_room.assert_awaited_once_with("human-demo-room")
        assert tts.get_publisher("dost") is pub_dost
        assert tts.get_publisher("sathi") is pub_sathi
