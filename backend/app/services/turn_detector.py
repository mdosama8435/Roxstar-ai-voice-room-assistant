import asyncio
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.config import settings
from app.observability.logger import get_logger
from app.schemas.contracts import (
    ConversationTurn,
    OrchestrationEvent,
    OrchestrationEventType,
    TranscriptEvent,
    TurnState,
)
from app.services.incomplete_utterance import is_incomplete_utterance

logger = get_logger("turn_detector")


class ActiveTurnRecord:
    """Internal tracker for an in-flight utterance turn."""
    def __init__(
        self,
        turn_id: str,
        room_id: str,
        participant_identity: str,
        participant_display_name: str,
        source: str = "voice",
        sequence: int = 0,
    ):
        self.turn_id = turn_id
        self.room_id = room_id
        self.participant_identity = participant_identity
        self.participant_display_name = participant_display_name
        self.source = source
        self.sequence = sequence
        self.transcript = ""
        self.language = "auto"
        self.language_confidence: Optional[float] = None
        self.state: TurnState = TurnState.SPEAKING
        self.started_at: datetime = datetime.now(timezone.utc)
        self.ended_at: datetime = datetime.now(timezone.utc)
        self.last_update_monotonic: float = time.monotonic()
        self.transcript_event_id: Optional[str] = None
        self.pause_started_at: Optional[float] = None


class TurnDetector:
    """
    Deterministic Turn Detection Engine.
    
    Transforms streaming partial and final TranscriptEvents into aggregated,
    structured ConversationTurns with pause handling, incomplete sentence awareness,
    and duplicate protection.
    """

    def __init__(self, pause_threshold_ms: Optional[int] = None):
        self.pause_threshold_ms = (
            pause_threshold_ms or settings.turn_pause_threshold_ms or 1500
        )
        # Active turn mapping: (room_id, participant_identity) -> ActiveTurnRecord
        self._active_turns: Dict[Tuple[str, str], ActiveTurnRecord] = {}
        # Bounded LRU cache of processed transcript event IDs to prevent duplicate processing
        self._processed_event_ids: OrderedDict[str, float] = OrderedDict()
        self._max_processed_ids = 5000
        self._lock = asyncio.Lock()
        self._sequence_counter: Dict[str, int] = {}

    def _next_sequence(self, room_id: str) -> int:
        count = self._sequence_counter.get(room_id, 0) + 1
        self._sequence_counter[room_id] = count
        return count

    def is_duplicate_event(self, event_id: Optional[str]) -> bool:
        if not event_id:
            return False
        return event_id in self._processed_event_ids

    def _mark_event_processed(self, event_id: Optional[str]) -> None:
        if not event_id:
            return
        self._processed_event_ids[event_id] = time.monotonic()
        if len(self._processed_event_ids) > self._max_processed_ids:
            self._processed_event_ids.popitem(last=False)

    async def process_transcript_event(
        self,
        event: TranscriptEvent,
    ) -> Tuple[Optional[ConversationTurn], List[OrchestrationEvent]]:
        """
        Processes an incoming partial or final TranscriptEvent.
        
        Returns:
            (completed_turn: Optional[ConversationTurn], lifecycle_events: List[OrchestrationEvent])
        """
        async with self._lock:
            # 1. Duplicate event protection
            if event.status == "final" and self.is_duplicate_event(event.event_id):
                logger.info(
                    "Duplicate final transcript event ignored",
                    extra={"room_id": event.room_id, "event_id": event.event_id}
                )
                return None, []

            now_utc = datetime.now(timezone.utc)
            now_mono = time.monotonic()
            key = (event.room_id, event.participant_identity)
            active = self._active_turns.get(key)
            lifecycle_events: List[OrchestrationEvent] = []

            # 2. Interim Partial Transcript Processing
            if event.status == "partial":
                if active is None:
                    # Initialize new active turn in SPEAKING state
                    seq = self._next_sequence(event.room_id)
                    active = ActiveTurnRecord(
                        turn_id=f"turn-{uuid.uuid4().hex[:12]}",
                        room_id=event.room_id,
                        participant_identity=event.participant_identity,
                        participant_display_name=event.participant_display_name,
                        source=event.modality.value.lower() if event.modality else "voice",
                        sequence=seq,
                    )
                    active.transcript = event.transcript
                    active.language = event.detected_language or "auto"
                    active.language_confidence = event.language_confidence
                    active.transcript_event_id = event.event_id
                    active.started_at = event.timestamp or now_utc
                    active.ended_at = now_utc
                    active.last_update_monotonic = now_mono
                    self._active_turns[key] = active

                    lifecycle_events.append(
                        OrchestrationEvent(
                            event_id=f"oevt-{uuid.uuid4().hex[:12]}",
                            event_type=OrchestrationEventType.TURN_STARTED,
                            room_id=event.room_id,
                            turn_id=active.turn_id,
                            participant_identity=event.participant_identity,
                            timestamp=now_utc,
                            payload={
                                "partial_text": event.transcript,
                                "state": TurnState.SPEAKING.value,
                                "sequence": seq,
                            },
                        )
                    )
                else:
                    # Update existing turn
                    if active.state == TurnState.PAUSED:
                        # Resumed speaking after pause
                        active.state = TurnState.SPEAKING
                        active.pause_started_at = None
                        lifecycle_events.append(
                            OrchestrationEvent(
                                event_id=f"oevt-{uuid.uuid4().hex[:12]}",
                                event_type=OrchestrationEventType.TURN_RESUMED,
                                room_id=event.room_id,
                                turn_id=active.turn_id,
                                participant_identity=event.participant_identity,
                                timestamp=now_utc,
                                payload={"resumed_text": event.transcript},
                            )
                        )

                    # Append or update transcript:
                    # If incoming partial starts with previous text, replace with longer text
                    active.transcript = event.transcript
                    active.language = event.detected_language or active.language
                    active.language_confidence = event.language_confidence or active.language_confidence
                    active.ended_at = now_utc
                    active.last_update_monotonic = now_mono
                    active.transcript_event_id = event.event_id

                return None, lifecycle_events

            # 3. Final Transcript Processing
            # Final transcript indicates explicit STT turn completion or text input
            self._mark_event_processed(event.event_id)

            if active is None:
                # Direct final arrived (e.g. text chat or short single-burst STT final)
                seq = self._next_sequence(event.room_id)
                turn_id = f"turn-{uuid.uuid4().hex[:12]}"
                duration_ms = event.latency_ms or 0.0
                turn = ConversationTurn(
                    turn_id=turn_id,
                    room_id=event.room_id,
                    participant_identity=event.participant_identity,
                    participant_display_name=event.participant_display_name,
                    transcript=event.transcript.strip(),
                    language=event.detected_language or "auto",
                    language_confidence=event.language_confidence,
                    started_at=event.timestamp or now_utc,
                    ended_at=now_utc,
                    duration_ms=duration_ms,
                    sequence=seq,
                    is_complete=True,
                    source="text" if (event.modality and "TEXT" in str(event.modality).upper()) else "voice",
                    transcript_event_id=event.event_id,
                )
            else:
                # Merge with active turn
                active.state = TurnState.COMPLETE
                active.transcript = event.transcript.strip()
                active.ended_at = now_utc
                duration_ms = (active.ended_at - active.started_at).total_seconds() * 1000.0
                turn = ConversationTurn(
                    turn_id=active.turn_id,
                    room_id=active.room_id,
                    participant_identity=active.participant_identity,
                    participant_display_name=active.participant_display_name,
                    transcript=active.transcript,
                    language=event.detected_language or active.language,
                    language_confidence=event.language_confidence or active.language_confidence,
                    started_at=active.started_at,
                    ended_at=active.ended_at,
                    duration_ms=round(duration_ms, 2),
                    sequence=active.sequence,
                    is_complete=True,
                    source=active.source,  # type: ignore[arg-type]
                    transcript_event_id=event.event_id,
                )
                del self._active_turns[key]

            lifecycle_events.append(
                OrchestrationEvent(
                    event_id=f"oevt-{uuid.uuid4().hex[:12]}",
                    event_type=OrchestrationEventType.TURN_COMPLETED,
                    room_id=turn.room_id,
                    turn_id=turn.turn_id,
                    participant_identity=turn.participant_identity,
                    timestamp=now_utc,
                    payload={
                        "transcript": turn.transcript,
                        "duration_ms": turn.duration_ms,
                        "sequence": turn.sequence,
                        "source": turn.source,
                    },
                )
            )

            return turn, lifecycle_events

    async def handle_pause_event(
        self,
        room_id: str,
        participant_identity: str,
    ) -> List[OrchestrationEvent]:
        """
        Marks an active turn as PAUSED.
        Does not finalize yet; allows continuation up to threshold.
        """
        async with self._lock:
            key = (room_id, participant_identity)
            active = self._active_turns.get(key)
            if not active or active.state != TurnState.SPEAKING:
                return []

            active.state = TurnState.PAUSED
            active.pause_started_at = time.monotonic()
            now_utc = datetime.now(timezone.utc)

            return [
                OrchestrationEvent(
                    event_id=f"oevt-{uuid.uuid4().hex[:12]}",
                    event_type=OrchestrationEventType.TURN_PAUSED,
                    room_id=room_id,
                    turn_id=active.turn_id,
                    participant_identity=participant_identity,
                    timestamp=now_utc,
                    payload={
                        "transcript_so_far": active.transcript,
                        "pause_threshold_ms": self.pause_threshold_ms,
                    },
                )
            ]

    def reset_room(self, room_id: str) -> None:
        """Cleans up active state for a given room."""
        to_delete = [k for k in self._active_turns.keys() if k[0] == room_id]
        for k in to_delete:
            del self._active_turns[k]
        self._sequence_counter.pop(room_id, None)


# Global turn detector singleton
turn_detector = TurnDetector()
