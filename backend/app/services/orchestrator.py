"""
Master Orchestration Coordinator for Phase 3B/3C/3D.

Pipeline Architecture:
Voice (STT) / Text (Auth Endpoint)
    ↓
TranscriptEvent
    ↓
TurnDetector (State machine + Pause continuation)
    ↓
ConversationTurn
    ↓
Context Update + Read-Only Snapshot
    ↓
Response Eligibility (Deterministic rules)
    ↓
Deterministic Bot Router (DOST vs SATHI)
    ↓
Turn Lock Manager (Room Mutex)
    ↓
[PHASE 3C: LLM RESPONSE GENERATION]
    ├── ConversationContextBuilder (Structured speaker & room context)
    ├── PersonaPromptBuilder (AI Dost vs AI Sathi prompts)
    ├── OutputValidator (Speech formatting & safety)
    └── LLMProvider Abstraction (Gemini / Mock)
    ↓
AI Response Text (Broadcast via LiveKit DataChannel to room UI)
    ↓
[PHASE 3D: TTS SYNTHESIS — TURN LOCK HELD THROUGH HERE]
    ├── TextChunker (sentence-boundary buffering)
    ├── SarvamTTSProvider (Bulbul v3, linear16 PCM, 24kHz, mono)
    └── LiveKitAudioPublisher (AudioFrame → AudioSource → LocalAudioTrack → Room)
    ↓
Release Turn Lock (Guaranteed in finally block)
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from livekit import api

from app.config import settings
from app.observability.logger import get_logger
from app.schemas.contracts import (
    BotRoutingDecision,
    BotType,
    ConversationTurn,
    LiveKitOrchestrationDataMessage,
    OrchestrationDecision,
    OrchestrationEvent,
    OrchestrationEventType,
    ResponseEligibility,
    TranscriptEvent,
    TriggerType,
    TurnState,
)
from app.schemas.llm import (
    AIResponseGeneratedEvent,
    LiveKitAIResponseChunkMessage,
    LiveKitAIResponseDataMessage,
)
from app.services.bot_router import bot_router
from app.services.conversation_context import (
    RoomContextSnapshot,
    conversation_context_manager,
)
from app.services.conversation_context_builder import ConversationContextBuilder
from app.services.llm.factory import get_llm_provider
from app.services.llm.output_validator import OutputValidator
from app.services.incomplete_utterance import is_incomplete_utterance
from app.services.response_eligibility import response_eligibility_service
from app.services.turn_detector import turn_detector
from app.services.turn_lock import turn_lock_manager

logger = get_logger("orchestrator")


class OrchestratorService:
    """
    Master Orchestration Coordinator managing the end-to-end conversational turn lifecycle,
    deterministic bot routing, turn locking, and LLM text response generation.
    """

    def __init__(self):
        self._event_listeners: List[Callable[[OrchestrationEvent], Any]] = []
        self._in_flight_turns: Set[str] = set()
        self._completed_llm_turns: Set[str] = set()
        self._cancelled_requests: Set[str] = set()
        self._active_llm_tasks: Dict[str, asyncio.Task] = {}
        self._completed_ai_responses: Dict[str, AIResponseGeneratedEvent] = {}
        # Phase 3D: TTS service and active TTS request tracking
        self._tts_service = None
        # AI LiveKit lifecycle (backend-owned publishers); may rejoin per human room
        self._ai_room_lifecycle = None
        # Maps turn_id -> active TTS request_id for barge-in cancellation
        self._active_tts_requests: Dict[str, str] = {}
        # Maps turn_id -> LLM request_id (for barge-in / cancel)
        self._llm_request_by_turn: Dict[str, str] = {}
        # Maps room_id -> turn_id currently generating/speaking
        self._active_turn_by_room: Dict[str, str] = {}
        # Structured TTS/audio events collected for tests / observability
        self._tts_events: List[Dict[str, Any]] = []

    def set_tts_service(self, tts_service) -> None:
        """
        Inject TTS service at runtime (Phase 3D).
        Called by application startup — not at import time.
        """
        self._tts_service = tts_service
        if tts_service is not None and hasattr(tts_service, "set_event_listener"):
            tts_service.set_event_listener(self._on_tts_event)
        logger.info("Phase 3D TTS service registered with orchestrator")

    def set_ai_room_lifecycle(self, lifecycle) -> None:
        """Inject AI LiveKit room lifecycle so TTS can publish into the human room."""
        self._ai_room_lifecycle = lifecycle
        logger.info(
            "Phase 3D AI room lifecycle registered with orchestrator",
            extra={"room_name": getattr(lifecycle, "room_name", None)},
        )

    async def _ensure_ai_publishers_for_room(self, room_id: str) -> bool:
        """
        Ensure AI Dost/Sathi are connected in ``room_id`` and rebound on TTSService.

        Returns True when at least one publisher is bound after ensure.
        """
        if self._tts_service is None:
            return False
        lifecycle = self._ai_room_lifecycle
        if lifecycle is None:
            logger.warning(
                "AI room lifecycle missing — TTS cannot publish LiveKit audio",
                extra={"room_id": room_id},
            )
            return bool(getattr(self._tts_service, "_publishers", None))

        try:
            await lifecycle.ensure_room(room_id)
        except Exception as exc:
            logger.error(
                "Failed to ensure AI participants in human room: %s",
                type(exc).__name__,
                extra={"room_id": room_id},
            )
            return False

        for session in lifecycle.sessions:
            self._tts_service.set_publisher(session.agent_id, session.publisher)
            logger.info(
                "AI publisher bound for TTS",
                extra={
                    "room_id": room_id,
                    "agent_id": session.agent_id,
                    "identity": session.identity,
                    "connected": session.is_connected,
                    "track_published": getattr(session, "is_track_published", False),
                },
            )
        return bool(self._tts_service._publishers)

    # Real TTS lifecycle events forwarded to LiveKit DataChannel (observability only).
    _TTS_BROADCAST_EVENTS = frozenset(
        {
            "tts.started",
            "tts.first_audio",
            "tts.completed",
            "tts.failed",
            "tts.error",
            "tts.cancelled",
            "audio.published",
            "audio.cancelled",
        }
    )

    def _on_tts_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Record structured TTS/audio events and forward lifecycle to the room UI."""
        record = {"event_type": event_type, **(payload or {})}
        self._tts_events.append(record)
        # Cap memory in long-running processes
        if len(self._tts_events) > 500:
            self._tts_events = self._tts_events[-250:]

        if event_type not in self._TTS_BROADCAST_EVENTS:
            return

        room_id = (payload or {}).get("room_id")
        if not room_id:
            return

        # Safe fields only — no secrets / no raw audio / no full text
        msg: Dict[str, Any] = {
            "type": "tts.event",
            "event_type": event_type,
            "room_name": room_id,
        }
        for key in (
            "request_id",
            "turn_id",
            "agent_id",
            "ttfa_ms",
            "total_ms",
            "error_category",
            "reason",
            "chunks",
            "bytes",
        ):
            val = (payload or {}).get(key)
            if val is not None:
                msg[key] = val

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug(
                "TTS event broadcast skipped (no running loop)",
                extra={"event_type": event_type, "room_id": room_id},
            )
            return

        loop.create_task(
            self._broadcast_to_livekit_room(
                room_id,
                json.dumps(msg).encode("utf-8"),
            )
        )

    def register_listener(self, listener: Callable[[OrchestrationEvent], Any]) -> None:
        """Registers an async or sync callback for emitted orchestration events."""
        self._event_listeners.append(listener)

    @staticmethod
    def should_barge_in_for_turn(turn: ConversationTurn) -> bool:
        """
        Decide whether a newly completed HUMAN turn should interrupt in-flight AI speech.

        Uses the same eligibility/intent classification as response routing:

        - Meaningful turns (question / request / explicit bot address / follow-up)
          → barge-in (cancel active LLM/TTS).
        - Acknowledgements → soft barge-in (stop talking; no new AI reply).
        - Casual / ambient STT (short OR long) → do NOT barge-in.
        - Incomplete utterances → do NOT barge-in.

        Does not invent confidence scores; relies on ResponseEligibilityService.
        """
        text = (turn.transcript or "").strip()
        is_inc, _ = is_incomplete_utterance(text)
        if is_inc:
            return False

        eligibility = response_eligibility_service.evaluate(turn, None)
        if eligibility.should_respond:
            return True
        if eligibility.trigger_type == TriggerType.ACKNOWLEDGEMENT:
            # Soft ack while AI speaks — stop talking, but no new AI reply.
            return True
        if eligibility.trigger_type == TriggerType.CASUAL_STATEMENT:
            # Ambient / unrelated banter must not cancel an in-flight response,
            # regardless of token length (short "Instagram" or longer casual STT).
            return False
        if eligibility.trigger_type == TriggerType.INCOMPLETE_UTTERANCE:
            return False
        return False

    def _notify_listeners(self, event: OrchestrationEvent) -> None:
        for listener in self._event_listeners:
            try:
                res = listener(event)
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception as e:
                logger.warning(f"Error in orchestration event listener: {e}")

    async def _broadcast_to_livekit_room(self, room_name: str, payload_bytes: bytes) -> None:
        """Broadcasts orchestration decisions and streaming chunks on topic 'orchestration.stream'."""
        if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
            return

        try:
            async with api.LiveKitAPI(
                settings.livekit_url,
                settings.livekit_api_key,
                settings.livekit_api_secret,
            ) as lk_api:
                kind_enum = getattr(api, "DataPacketKind", None)
                packet_kind = getattr(kind_enum, "RELIABLE", 0) if kind_enum else 0
                req = api.SendDataRequest(
                    room=room_name,
                    data=payload_bytes,
                    kind=packet_kind,
                    topic="orchestration.stream",
                )
                await lk_api.room.send_data(req)
        except Exception as exc:
            logger.warning(
                f"Failed to broadcast orchestration event to LiveKit DataChannel: {exc}",
                extra={"room_id": room_name}
            )

    async def cancel_generation(self, request_id: str) -> None:
        """
        Signals cancellation of an active generation request (LLM + TTS).

        Phase 3D barge-in semantics:
        1. Mark LLM request as cancelled (prevents late publication / TTS start)
        2. Cancel active TTS request(s) and clear audio queues
        3. Cancel in-flight asyncio LLM tasks bound to that request
        4. Turn lock released by generate_and_broadcast finally (or interrupt_room)
        """
        logger.info(f"Signaling cancellation for request_id={request_id}")
        self._cancelled_requests.add(request_id)

        try:
            provider = get_llm_provider()
            await provider.cancel(request_id)
        except Exception as e:
            logger.warning(f"Error notifying LLM provider of cancellation: {e}")

        # Cancel any TTS tied to a turn that owns this LLM request
        for turn_id, llm_req in list(self._llm_request_by_turn.items()):
            if llm_req != request_id:
                continue
            tts_request_id = self._active_tts_requests.get(turn_id)
            if self._tts_service is not None and tts_request_id:
                try:
                    await self._tts_service.cancel(
                        tts_request_id, reason=f"llm_cancelled:{request_id}"
                    )
                except Exception as tts_cancel_err:
                    logger.warning(
                        f"Error cancelling TTS for turn {turn_id}: {tts_cancel_err}"
                    )
            task = self._active_llm_tasks.get(turn_id)
            if task is not None and not task.done():
                task.cancel()

        # Direct TTS request_id cancel (when tests register TTS id only)
        if self._tts_service is not None:
            for turn_id, tts_request_id in list(self._active_tts_requests.items()):
                if tts_request_id == request_id:
                    try:
                        await self._tts_service.cancel(
                            tts_request_id, reason=f"cancelled:{request_id}"
                        )
                    except Exception:
                        pass
                    break

    async def interrupt_room_generation(
        self,
        room_id: str,
        reason: str = "barge_in",
    ) -> bool:
        """
        Barge-in: cancel active LLM + TTS for a room, clear audio, release lock.

        Returns True if an active generation was interrupted.
        Old response must never resume after this returns.
        """
        turn_id = self._active_turn_by_room.get(room_id)
        if not turn_id:
            # Still force-release a stale lock if present
            locked = await turn_lock_manager.is_locked(room_id)
            if locked:
                await turn_lock_manager.release(room_id)
                return True
            return False

        logger.info(
            "barge_in.interrupt",
            extra={"room_id": room_id, "turn_id": turn_id, "reason": reason},
        )

        llm_req = self._llm_request_by_turn.get(turn_id)
        if llm_req:
            self._cancelled_requests.add(llm_req)
            try:
                provider = get_llm_provider()
                await provider.cancel(llm_req)
            except Exception as e:
                logger.warning(f"Barge-in LLM cancel notify failed: {e}")

        tts_req = self._active_tts_requests.get(turn_id)
        if self._tts_service is not None and tts_req:
            try:
                await self._tts_service.cancel(tts_req, reason=reason)
            except Exception as e:
                logger.warning(f"Barge-in TTS cancel failed: {e}")

        task = self._active_llm_tasks.get(turn_id)
        if task is not None and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=0.5)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass

        try:
            await turn_lock_manager.release(room_id)
        except Exception as e:
            logger.warning(f"Barge-in lock release failed: {e}")

        self._active_turn_by_room.pop(room_id, None)
        self._active_tts_requests.pop(turn_id, None)
        # Keep llm_request_by_turn until generate finally cleans; mark cancelled already
        self._in_flight_turns.discard(turn_id)
        return True

    async def await_llm_response(
        self,
        turn_id: str,
        timeout: float = 15.0,
    ) -> Optional[AIResponseGeneratedEvent]:
        """
        Helper method allowing test callers and handlers to await completion of an active LLM generation.
        """
        task = self._active_llm_tasks.get(turn_id)
        if task and not task.done():
            try:
                return await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"Awaiting LLM response for turn {turn_id} timed out after {timeout}s")
                return None
            except Exception as exc:
                logger.error(f"Error awaiting LLM response task for turn {turn_id}: {exc}")
                return None
        return self._completed_ai_responses.get(turn_id)

    async def generate_and_broadcast_ai_response(
        self,
        decision: OrchestrationDecision,
        turn: ConversationTurn,
        snapshot: RoomContextSnapshot,
        turn_completed_perf: Optional[float] = None,
    ) -> Optional[AIResponseGeneratedEvent]:
        """
        Executes Phase 3C LLM text response generation downstream of turn lock acquisition.
        
        Lifecycle:
        1. Assemble structured multi-turn context and persona prompt
        2. Stream tokens from LLMProvider
        3. Emit first-token and stream preview chunks to room DataChannel
        4. Validate text through OutputValidator
        5. Record AI turn in conversation context
        6. Broadcast canonical AI response message
        7. Release TurnLock in guaranteed finally block
        """
        t_llm_start = time.perf_counter()
        selected_bot = decision.routing.selected_bot
        llm_request = ConversationContextBuilder.build_request(
            decision=decision,
            snapshot=snapshot,
            turn=turn,
        )

        # Track active generation for barge-in (room-scoped, single speaker)
        self._llm_request_by_turn[turn.turn_id] = llm_request.request_id
        self._active_turn_by_room[turn.room_id] = turn.turn_id

        # Notify start event
        start_event = OrchestrationEvent(
            event_id=f"oevt-{uuid.uuid4().hex[:12]}",
            event_type=OrchestrationEventType.LLM_REQUEST_STARTED,
            room_id=turn.room_id,
            turn_id=turn.turn_id,
            participant_identity=turn.participant_identity,
            timestamp=datetime.now(timezone.utc),
            payload={
                "request_id": llm_request.request_id,
                "selected_bot": selected_bot.value,
                "model": settings.llm_model,
                "provider": settings.llm_provider,
            },
        )
        self._notify_listeners(start_event)

        accumulated_chunks: List[str] = []
        t_first_token: Optional[float] = None
        first_token_latency_ms: Optional[float] = None

        try:
            # Check pre-generation cancellation
            if llm_request.request_id in self._cancelled_requests:
                logger.info(f"Request {llm_request.request_id} cancelled prior to provider execution")
                return None

            provider = get_llm_provider()

            async for chunk in provider.stream(llm_request):
                # Check for cancellation during streaming
                if llm_request.request_id in self._cancelled_requests:
                    logger.info(f"Request {llm_request.request_id} cancelled during stream; breaking loop")
                    break

                if t_first_token is None and chunk.text_delta:
                    t_first_token = time.perf_counter()
                    first_token_latency_ms = round((t_first_token - t_llm_start) * 1000.0, 2)
                    first_token_evt = OrchestrationEvent(
                        event_id=f"oevt-{uuid.uuid4().hex[:12]}",
                        event_type=OrchestrationEventType.LLM_FIRST_TOKEN,
                        room_id=turn.room_id,
                        turn_id=turn.turn_id,
                        participant_identity=turn.participant_identity,
                        timestamp=datetime.now(timezone.utc),
                        payload={
                            "request_id": llm_request.request_id,
                            "first_token_latency_ms": first_token_latency_ms,
                            "bot": selected_bot.value,
                        },
                    )
                    self._notify_listeners(first_token_evt)

                accumulated_chunks.append(chunk.text_delta)

                # Broadcast ephemeral streaming chunk preview (does NOT create permanent chat message)
                chunk_msg = LiveKitAIResponseChunkMessage(
                    request_id=llm_request.request_id,
                    room_name=turn.room_id,
                    bot=selected_bot.value,
                    sequence=chunk.sequence,
                    text_delta=chunk.text_delta,
                    is_final=chunk.is_final,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                asyncio.create_task(
                    self._broadcast_to_livekit_room(
                        turn.room_id,
                        chunk_msg.model_dump_json().encode("utf-8"),
                    )
                )

            # Check post-stream cancellation (anti-race condition)
            if llm_request.request_id in self._cancelled_requests:
                logger.info(
                    f"Request {llm_request.request_id} was cancelled before finalization; suppressing publication"
                )
                cancel_evt = OrchestrationEvent(
                    event_id=f"oevt-{uuid.uuid4().hex[:12]}",
                    event_type=OrchestrationEventType.LLM_CANCELLED,
                    room_id=turn.room_id,
                    turn_id=turn.turn_id,
                    participant_identity=turn.participant_identity,
                    timestamp=datetime.now(timezone.utc),
                    payload={"request_id": llm_request.request_id, "bot": selected_bot.value},
                )
                self._notify_listeners(cancel_evt)
                return None

            # Validate and clean assembled text
            raw_text = "".join(accumulated_chunks).strip()
            try:
                validated_text = OutputValidator.validate(raw_text)
            except Exception as val_exc:
                logger.warning(
                    f"Output validation failed for turn {turn.turn_id}: {val_exc} — "
                    "suppressing TTS and canonical AI publication"
                )
                fail_evt = OrchestrationEvent(
                    event_id=f"oevt-{uuid.uuid4().hex[:12]}",
                    event_type=OrchestrationEventType.LLM_RESPONSE_FAILED,
                    room_id=turn.room_id,
                    turn_id=turn.turn_id,
                    participant_identity=turn.participant_identity,
                    timestamp=datetime.now(timezone.utc),
                    payload={
                        "request_id": llm_request.request_id,
                        "bot": selected_bot.value,
                        "error": f"validation_failed:{type(val_exc).__name__}",
                    },
                )
                self._notify_listeners(fail_evt)
                return None

            if not validated_text or not str(validated_text).strip():
                logger.warning(
                    f"Validated LLM text empty for turn {turn.turn_id} — "
                    "no TTS, no duplicate generation"
                )
                return None

            # Cancelled after validation — do not publish text/audio
            if llm_request.request_id in self._cancelled_requests:
                logger.info(
                    f"Request {llm_request.request_id} cancelled after validation; "
                    "suppressing publication and TTS"
                )
                return None

            t_llm_complete = time.perf_counter()
            llm_queue_latency_ms = (
                round((t_llm_start - turn_completed_perf) * 1000.0, 2)
                if turn_completed_perf is not None
                else 0.0
            )
            llm_completion_latency_ms = round((t_llm_complete - t_llm_start) * 1000.0, 2)
            total_pipeline_latency_ms = (
                round((t_llm_complete - turn_completed_perf) * 1000.0, 2)
                if turn_completed_perf is not None
                else llm_completion_latency_ms
            )

            bot_display_name = (
                "RoxStar AI Dost"
                if selected_bot == BotType.DOST
                else "RoxStar AI Sathi"
            )

            # Extract provider execution metadata (accounting for failover)
            p_meta = provider.get_metadata(llm_request.request_id) if hasattr(provider, "get_metadata") else None
            actual_provider = (p_meta.get("final_provider") if p_meta else None) or getattr(provider, "name", settings.llm_provider)
            actual_model = settings.nvidia_model if actual_provider == "nvidia" else settings.llm_model

            ai_event = AIResponseGeneratedEvent(
                event_id=f"aievt-{uuid.uuid4().hex[:12]}",
                request_id=llm_request.request_id,
                room_id=turn.room_id,
                bot=selected_bot,
                responding_to_turn_id=turn.turn_id,
                text=validated_text,
                model=actual_model,
                provider=actual_provider,
                latency_ms=total_pipeline_latency_ms,
                first_token_latency_ms=first_token_latency_ms,
                timestamp=datetime.now(timezone.utc),
            )

            # Store completed response
            self._completed_ai_responses[turn.turn_id] = ai_event

            # Record AI response turn in active room context
            ai_turn = ConversationTurn(
                turn_id=f"turn-ai-{uuid.uuid4().hex[:8]}",
                room_id=turn.room_id,
                participant_identity=f"ai_{selected_bot.value.lower()}",
                participant_display_name=bot_display_name,
                transcript=validated_text,
                state=TurnState.COMPLETE,
                is_final=True,
            )
            await conversation_context_manager.add_turn(ai_turn)

            # Broadcast ONE canonical AI response message over LiveKit DataChannel
            broadcast_msg = LiveKitAIResponseDataMessage(
                event_id=ai_event.event_id,
                request_id=llm_request.request_id,
                room_name=turn.room_id,
                bot=selected_bot.value,
                bot_display_name=bot_display_name,
                responding_to_turn_id=turn.turn_id,
                text=validated_text,
                model=actual_model,
                latency_ms=total_pipeline_latency_ms,
                timestamp=ai_event.timestamp.isoformat(),
            )
            asyncio.create_task(
                self._broadcast_to_livekit_room(
                    turn.room_id,
                    broadcast_msg.model_dump_json().encode("utf-8"),
                )
            )

            # ----------------------------------------------------------------
            # Phase 3D: TTS — lock still held. Exactly ONE canonical text above.
            # TTS failure / cancel must NOT trigger another LLM generation.
            # Only the selected bot's publisher may receive audio.
            # ----------------------------------------------------------------
            if (
                self._tts_service is not None
                and llm_request.request_id not in self._cancelled_requests
            ):
                try:
                    from app.schemas.tts import TTSRequest as _TTSRequest

                    publishers_ready = await self._ensure_ai_publishers_for_room(turn.room_id)
                    if not publishers_ready:
                        logger.error(
                            "Phase 3D TTS skipped: no AI LiveKit publishers bound "
                            f"(room={turn.room_id}, bot={selected_bot.value}) — "
                            "canonical text remains valid"
                        )

                    _tts_speaker = (
                        settings.sarvam_tts_dost_speaker
                        if selected_bot == BotType.DOST
                        else settings.sarvam_tts_sathi_speaker
                    )
                    _tts_request = _TTSRequest(
                        request_id=f"tts-{uuid.uuid4().hex[:12]}",
                        turn_id=turn.turn_id,
                        agent_id=selected_bot.value.lower(),
                        text=validated_text,
                        speaker=_tts_speaker,
                        language_code=settings.sarvam_tts_language,
                        model=settings.sarvam_tts_model,
                        room_id=turn.room_id,
                    )
                    self._active_tts_requests[turn.turn_id] = _tts_request.request_id

                    # Final cancel check before starting TTS
                    if llm_request.request_id in self._cancelled_requests:
                        await self._tts_service.cancel(
                            _tts_request.request_id, reason="cancelled_before_tts"
                        )
                    elif not publishers_ready:
                        logger.warning(
                            f"Phase 3D TTS not started (publisher missing) for turn {turn.turn_id}"
                        )
                    else:
                        logger.info(
                            f"Phase 3D TTS starting: turn={turn.turn_id}, "
                            f"bot={selected_bot.value}, speaker={_tts_speaker}, "
                            f"model={settings.sarvam_tts_model}, room={turn.room_id}"
                        )
                        tts_metrics = await self._tts_service.synthesize_and_publish(
                            _tts_request
                        )

                        # If cancelled mid-TTS, do not treat as success / do not resume
                        if llm_request.request_id in self._cancelled_requests:
                            logger.info(
                                f"TTS interrupted by barge-in for turn {turn.turn_id}"
                            )
                        elif tts_metrics and tts_metrics.status.value == "COMPLETED":
                            e2e_ms = None
                            if turn_completed_perf is not None and tts_metrics.tts_completion_at:
                                e2e_ms = round(
                                    (tts_metrics.tts_completion_at - turn_completed_perf)
                                    * 1000.0,
                                    2,
                                )
                            logger.info(
                                f"Phase 3D TTS completed: turn={turn.turn_id}, "
                                f"ttfa_ms={tts_metrics.time_to_first_audio_ms}, "
                                f"total_ms={tts_metrics.tts_total_ms}, "
                                f"e2e_ms={e2e_ms}"
                            )
                        else:
                            logger.warning(
                                f"Phase 3D TTS failed for turn {turn.turn_id} — "
                                "canonical text response remains valid, no LLM retry"
                            )

                except asyncio.CancelledError:
                    logger.info(f"TTS task CancelledError for turn {turn.turn_id}")
                    if self._tts_service is not None:
                        tts_id = self._active_tts_requests.get(turn.turn_id)
                        if tts_id:
                            await self._tts_service.cancel(tts_id, reason="task_cancelled")
                    raise
                except Exception as tts_exc:
                    logger.error(
                        f"Phase 3D TTS pipeline error for turn {turn.turn_id}: {tts_exc}",
                        extra={"turn_id": turn.turn_id, "room_id": turn.room_id},
                    )
                finally:
                    self._active_tts_requests.pop(turn.turn_id, None)

            # Emit completion event
            completed_evt = OrchestrationEvent(
                event_id=f"oevt-{uuid.uuid4().hex[:12]}",
                event_type=OrchestrationEventType.LLM_RESPONSE_COMPLETED,
                room_id=turn.room_id,
                turn_id=turn.turn_id,
                participant_identity=turn.participant_identity,
                timestamp=ai_event.timestamp,
                payload={
                    "request_id": llm_request.request_id,
                    "bot": selected_bot.value,
                    "text": validated_text,
                    "metrics": {
                        "llm_queue_latency_ms": llm_queue_latency_ms,
                        "llm_first_token_latency_ms": first_token_latency_ms,
                        "llm_completion_latency_ms": llm_completion_latency_ms,
                        "total_pipeline_latency_ms": total_pipeline_latency_ms,
                    },
                },
            )
            self._notify_listeners(completed_evt)

            logger.info(
                f"Phase 3C AI response generated ({turn.room_id}): bot={selected_bot.value}, "
                f"latency={total_pipeline_latency_ms}ms, first_token={first_token_latency_ms}ms",
                extra={
                    "room_id": turn.room_id,
                    "turn_id": turn.turn_id,
                    "bot": selected_bot.value,
                    "total_latency_ms": total_pipeline_latency_ms,
                }
            )

            return ai_event

        except asyncio.CancelledError:
            logger.info(
                f"LLM/TTS generation CancelledError for turn {turn.turn_id} "
                f"(barge-in or task cancel)"
            )
            # Ensure TTS is stopped; do not resume
            tts_id = self._active_tts_requests.get(turn.turn_id)
            if self._tts_service is not None and tts_id:
                try:
                    await self._tts_service.cancel(tts_id, reason="task_cancelled")
                except Exception:
                    pass
            cancel_evt = OrchestrationEvent(
                event_id=f"oevt-{uuid.uuid4().hex[:12]}",
                event_type=OrchestrationEventType.LLM_CANCELLED,
                room_id=turn.room_id,
                turn_id=turn.turn_id,
                participant_identity=turn.participant_identity,
                timestamp=datetime.now(timezone.utc),
                payload={
                    "request_id": llm_request.request_id,
                    "bot": selected_bot.value,
                    "reason": "cancelled",
                },
            )
            self._notify_listeners(cancel_evt)
            return None

        except Exception as exc:
            logger.error(
                f"Phase 3C LLM generation failed for turn {turn.turn_id}: {exc}",
                exc_info=True,
                extra={"room_id": turn.room_id, "turn_id": turn.turn_id}
            )
            fail_evt = OrchestrationEvent(
                event_id=f"oevt-{uuid.uuid4().hex[:12]}",
                event_type=OrchestrationEventType.LLM_RESPONSE_FAILED,
                room_id=turn.room_id,
                turn_id=turn.turn_id,
                participant_identity=turn.participant_identity,
                timestamp=datetime.now(timezone.utc),
                payload={
                    "request_id": llm_request.request_id,
                    "bot": selected_bot.value,
                    "error": str(exc),
                },
            )
            self._notify_listeners(fail_evt)
            return None

        finally:
            # Unconditional release of turn lock in guaranteed finally cleanup
            try:
                await turn_lock_manager.release(
                    room_id=turn.room_id,
                    bot=selected_bot,
                    turn_id=turn.turn_id,
                )
                logger.info(f"Turn lock released for {selected_bot.value} on turn {turn.turn_id}")
            except Exception as lock_err:
                logger.warning(f"Error releasing turn lock: {lock_err}")

            self._in_flight_turns.discard(turn.turn_id)
            self._completed_llm_turns.add(turn.turn_id)
            self._active_tts_requests.pop(turn.turn_id, None)
            self._llm_request_by_turn.pop(turn.turn_id, None)
            if self._active_turn_by_room.get(turn.room_id) == turn.turn_id:
                self._active_turn_by_room.pop(turn.room_id, None)
            self._active_llm_tasks.pop(turn.turn_id, None)

    async def handle_transcript_event(
        self,
        event: TranscriptEvent,
    ) -> Optional[OrchestrationDecision]:
        """
        Main entrypoint processing a streaming TranscriptEvent through the full pipeline.
        
        Fault isolation guarantee:
        Any exception is caught, logged with structured details, and fails closed
        without propagating errors to callers (preserving WebRTC/STT transport).
        """
        t_received = time.perf_counter()
        now_utc = datetime.now(timezone.utc)

        try:
            # 1. Turn Detection
            completed_turn, turn_events = await turn_detector.process_transcript_event(event)

            for tevt in turn_events:
                self._notify_listeners(tevt)

            if completed_turn is None:
                # Still intermediate/partial or duplicate: no completed turn
                return None

            t_turn_completed = time.perf_counter()

            # Barge-in: a meaningful new HUMAN turn interrupts active AI speech.
            # Ambient short casual STT finals must NOT cancel an in-flight response.
            is_human = not str(completed_turn.participant_identity).lower().startswith("ai_")
            if (
                is_human
                and completed_turn.room_id in self._active_turn_by_room
                and self.should_barge_in_for_turn(completed_turn)
            ):
                await self.interrupt_room_generation(
                    completed_turn.room_id, reason="barge_in"
                )

            # Emit TURN_COMPLETED event
            turn_completed_event = OrchestrationEvent(
                event_id=f"oevt-{uuid.uuid4().hex[:12]}",
                event_type=OrchestrationEventType.TURN_COMPLETED,
                room_id=completed_turn.room_id,
                participant_identity=completed_turn.participant_identity,
                turn_id=completed_turn.turn_id,
                timestamp=now_utc,
                payload={
                    "transcript": completed_turn.transcript,
                    "duration_ms": completed_turn.duration_ms,
                    "source": completed_turn.source,
                },
            )
            self._notify_listeners(turn_completed_event)

            # 2. Context Update + Read-Only Snapshot
            await conversation_context_manager.add_turn(completed_turn)
            context_snapshot: RoomContextSnapshot = await conversation_context_manager.get_context_snapshot(
                completed_turn.room_id
            )

            # 3. Response Eligibility Evaluation (with access to previous room context)
            eligibility: ResponseEligibility = response_eligibility_service.evaluate(
                turn=completed_turn,
                context=context_snapshot,
            )
            t_eligibility_decided = time.perf_counter()

            elig_event = OrchestrationEvent(
                event_id=f"oevt-{uuid.uuid4().hex[:12]}",
                event_type=OrchestrationEventType.RESPONSE_ELIGIBILITY_EVALUATED,
                room_id=completed_turn.room_id,
                turn_id=completed_turn.turn_id,
                participant_identity=completed_turn.participant_identity,
                timestamp=datetime.now(timezone.utc),
                payload={
                    "should_respond": eligibility.should_respond,
                    "trigger_type": eligibility.trigger_type.value,
                    "reason": eligibility.reason,
                    "confidence": eligibility.confidence,
                },
            )
            self._notify_listeners(elig_event)

            # 4. Single-Bot Routing
            routing: BotRoutingDecision = bot_router.route(
                turn=completed_turn,
                eligibility=eligibility,
                context=context_snapshot,
            )
            t_routing_decided = time.perf_counter()

            route_event = OrchestrationEvent(
                event_id=f"oevt-{uuid.uuid4().hex[:12]}",
                event_type=OrchestrationEventType.BOT_ROUTING_DECIDED,
                room_id=completed_turn.room_id,
                turn_id=completed_turn.turn_id,
                participant_identity=completed_turn.participant_identity,
                timestamp=datetime.now(timezone.utc),
                payload={
                    "selected_bot": routing.selected_bot.value,
                    "reason": routing.reason,
                    "routing_source": routing.routing_source,
                    "confidence": routing.confidence,
                },
            )
            self._notify_listeners(route_event)

            # 5. Turn Lock Acquisition
            lock_acquired = False
            lock_deferred = False
            t_lock_acquired: Optional[float] = None

            if eligibility.should_respond and routing.selected_bot != BotType.NONE:
                lock_acquired = await turn_lock_manager.acquire(
                    room_id=completed_turn.room_id,
                    bot=routing.selected_bot,
                    turn_id=completed_turn.turn_id,
                )
                t_lock_acquired = time.perf_counter()

                # If still blocked after barge-in attempt above, force interrupt + retry once
                if not lock_acquired:
                    await self.interrupt_room_generation(
                        completed_turn.room_id, reason="barge_in_lock_retry"
                    )
                    lock_acquired = await turn_lock_manager.acquire(
                        room_id=completed_turn.room_id,
                        bot=routing.selected_bot,
                        turn_id=completed_turn.turn_id,
                    )
                    t_lock_acquired = time.perf_counter()

                if lock_acquired:
                    lock_event = OrchestrationEvent(
                        event_id=f"oevt-{uuid.uuid4().hex[:12]}",
                        event_type=OrchestrationEventType.TURN_LOCK_ACQUIRED,
                        room_id=completed_turn.room_id,
                        turn_id=completed_turn.turn_id,
                        participant_identity=completed_turn.participant_identity,
                        timestamp=datetime.now(timezone.utc),
                        payload={"bot": routing.selected_bot.value},
                    )
                else:
                    lock_deferred = True
                    lock_event = OrchestrationEvent(
                        event_id=f"oevt-{uuid.uuid4().hex[:12]}",
                        event_type=OrchestrationEventType.TURN_LOCK_BLOCKED,
                        room_id=completed_turn.room_id,
                        turn_id=completed_turn.turn_id,
                        participant_identity=completed_turn.participant_identity,
                        timestamp=datetime.now(timezone.utc),
                        payload={
                            "bot": routing.selected_bot.value,
                            "reason": "room_response_locked",
                            "deferred": True,
                        },
                    )
                self._notify_listeners(lock_event)

            # 6. Assemble Latency Metrics
            stt_to_turn_ms = round((t_turn_completed - t_received) * 1000.0, 2)
            turn_to_elig_ms = round((t_eligibility_decided - t_turn_completed) * 1000.0, 2)
            elig_to_route_ms = round((t_routing_decided - t_eligibility_decided) * 1000.0, 2)
            route_to_lock_ms = (
                round((t_lock_acquired - t_routing_decided) * 1000.0, 2)
                if t_lock_acquired is not None
                else None
            )

            metrics: Dict[str, Any] = {
                "stt_to_turn_ms": stt_to_turn_ms,
                "turn_to_eligibility_ms": turn_to_elig_ms,
                "eligibility_to_routing_ms": elig_to_route_ms,
                "routing_to_lock_ms": route_to_lock_ms,
            }

            # 7. Final Orchestration Decision
            decision = OrchestrationDecision(
                decision_id=f"dec-{uuid.uuid4().hex[:12]}",
                room_id=completed_turn.room_id,
                turn_id=completed_turn.turn_id,
                eligibility=eligibility,
                routing=routing,
                context_snapshot_id=context_snapshot.snapshot_id,
                turn_lock_acquired=lock_acquired,
                created_at=datetime.now(timezone.utc),
            )

            decision_event = OrchestrationEvent(
                event_id=f"oevt-{uuid.uuid4().hex[:12]}",
                event_type=OrchestrationEventType.ORCHESTRATION_DECISION,
                room_id=decision.room_id,
                turn_id=decision.turn_id,
                participant_identity=completed_turn.participant_identity,
                timestamp=decision.created_at,
                payload={
                    "decision_id": decision.decision_id,
                    "should_respond": decision.eligibility.should_respond,
                    "selected_bot": decision.routing.selected_bot.value,
                    "turn_lock_acquired": decision.turn_lock_acquired,
                    "lock_deferred": lock_deferred,
                    "metrics": metrics,
                },
            )
            self._notify_listeners(decision_event)

            # 8. Broadcast over LiveKit DataChannel
            broadcast_msg = LiveKitOrchestrationDataMessage(
                event_id=decision_event.event_id,
                room_name=decision.room_id,
                turn_id=decision.turn_id,
                participant_identity=completed_turn.participant_identity,
                participant_display_name=completed_turn.participant_display_name,
                transcript=completed_turn.transcript,
                should_respond=decision.eligibility.should_respond,
                trigger_type=decision.eligibility.trigger_type.value,
                selected_bot=decision.routing.selected_bot.value,
                routing_reason=decision.routing.reason,
                turn_lock_acquired=decision.turn_lock_acquired,
                lock_deferred=lock_deferred,
                metrics=metrics,
                timestamp=decision.created_at.isoformat(),
            )
            asyncio.create_task(
                self._broadcast_to_livekit_room(
                    completed_turn.room_id,
                    broadcast_msg.model_dump_json().encode("utf-8"),
                )
            )

            logger.info(
                f"Orchestration decision produced ({completed_turn.room_id}): "
                f"respond={decision.eligibility.should_respond}, bot={decision.routing.selected_bot.value}, "
                f"locked={decision.turn_lock_acquired}",
                extra={
                    "room_id": completed_turn.room_id,
                    "turn_id": completed_turn.turn_id,
                    "bot": decision.routing.selected_bot.value,
                    "metrics": metrics,
                }
            )

            # 9. Phase 3C: Trigger Real LLM Response Generation if locked and eligible
            if (
                decision.eligibility.should_respond
                and decision.routing.selected_bot != BotType.NONE
                and decision.turn_lock_acquired
            ):
                # Enforce idempotency: prevent duplicate execution of the same turn
                if (
                    completed_turn.turn_id not in self._in_flight_turns
                    and completed_turn.turn_id not in self._completed_llm_turns
                ):
                    self._in_flight_turns.add(completed_turn.turn_id)
                    llm_task = asyncio.create_task(
                        self.generate_and_broadcast_ai_response(
                            decision=decision,
                            turn=completed_turn,
                            snapshot=context_snapshot,
                            turn_completed_perf=t_turn_completed,
                        )
                    )

                    def _llm_task_done(task: asyncio.Task, *, _turn_id: str = completed_turn.turn_id) -> None:
                        try:
                            exc = task.exception()
                        except asyncio.CancelledError:
                            return
                        if exc is not None:
                            logger.error(
                                f"LLM background task failed for turn {_turn_id}: {exc}",
                                exc_info=exc,
                            )

                    llm_task.add_done_callback(_llm_task_done)
                    self._active_llm_tasks[completed_turn.turn_id] = llm_task
                else:
                    logger.info(
                        f"Idempotency: Skipping duplicate LLM generation for turn {completed_turn.turn_id}"
                    )

            return decision

        except Exception as exc:
            logger.error(
                f"Fault isolation: Orchestration pipeline error: {exc}",
                exc_info=True,
                extra={"room_id": event.room_id, "event_id": event.event_id}
            )
            # Fail closed: return safe non-responding fallback
            return OrchestrationDecision(
                decision_id=f"dec-{uuid.uuid4().hex[:12]}",
                room_id=event.room_id,
                turn_id=f"err-{uuid.uuid4().hex[:8]}",
                eligibility=ResponseEligibility(
                    should_respond=False,
                    reason=f"pipeline_error_isolated:{str(exc)}",
                    confidence=1.0,
                    trigger_type=TriggerType.UNKNOWN,
                ),
                routing=BotRoutingDecision(
                    decision_id=f"route-err-{uuid.uuid4().hex[:8]}",
                    room_id=event.room_id,
                    turn_id="err",
                    selected_bot=BotType.NONE,
                    reason="fail_closed_error",
                    confidence=1.0,
                    routing_source="fallback",
                ),
                turn_lock_acquired=False,
                created_at=datetime.now(timezone.utc),
            )


# Global orchestrator singleton
orchestrator = OrchestratorService()
