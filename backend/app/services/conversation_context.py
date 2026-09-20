import asyncio
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.config import settings
from app.observability.logger import get_logger
from app.schemas.contracts import (
    ConversationTurn,
    SpeakerProfile,
)

logger = get_logger("conversation_context")


class ContextSnapshot(BaseModel):
    """
    Immutable read-only snapshot of room and speaker state provided to
    eligibility and router components before decision making.
    """
    snapshot_id: str
    room_id: str
    previous_turn: Optional[ConversationTurn] = None
    recent_turns: List[ConversationTurn] = Field(default_factory=list)
    current_topic: Optional[str] = None
    active_speaker_id: Optional[str] = None
    speaker_profile: Optional[SpeakerProfile] = None
    all_speaker_profiles: Dict[str, SpeakerProfile] = Field(default_factory=dict)
    turn_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def active_turns(self) -> List[ConversationTurn]:
        return self.recent_turns

    @property
    def speaker_profiles(self) -> Dict[str, SpeakerProfile]:
        return self.all_speaker_profiles


RoomContextSnapshot = ContextSnapshot


class RoomMemoryState:
    """Bounded, ephemeral in-memory state for an active voice room."""
    def __init__(self, room_id: str, max_turns: int = 20):
        self.room_id = room_id
        self.max_turns = max_turns
        self.recent_turns: List[ConversationTurn] = []
        # Keyed strictly by opaque participant_identity (never display name)
        self.speaker_profiles: Dict[str, SpeakerProfile] = {}
        self.current_topic: Optional[str] = None
        self.active_speaker_id: Optional[str] = None
        self.last_selected_bot: Optional[str] = None
        self.sequence: int = 0


class ConversationContextManager:
    """
    Ephemeral In-Memory Multi-User Room Context Service.
    
    Responsibilities:
    - Bounded FIFO turn retention (MAX_CONTEXT_TURNS default 20)
    - Strict speaker separation (profiles & facts isolated by participant_identity)
    - Topic inference heuristics for follow-up recognition
    - Emits immutable ContextSnapshot preceding eligibility classification
    - Zero persistent database / zero vector store in Phase 3B
    """

    def __init__(self, max_turns: Optional[int] = None):
        self.max_turns = max_turns or settings.max_context_turns or 20
        self._rooms: Dict[str, RoomMemoryState] = {}
        self._lock = asyncio.Lock()

    def _get_or_create_room(self, room_id: str) -> RoomMemoryState:
        if room_id not in self._rooms:
            self._rooms[room_id] = RoomMemoryState(room_id, max_turns=self.max_turns)
        return self._rooms[room_id]

    def _extract_simple_facts(self, text: str) -> List[str]:
        """Simple deterministic heuristics extracting self-disclosed speaker facts."""
        facts: List[str] = []
        lower = text.lower().strip()

        # Name disclosures: "my name is Rahul", "mera naam Rahul hai", "I am Rahul"
        name_match = re.search(r"(?:my name is|mera naam|i am|main hoon)\s+([A-Z][a-z]+|[a-z]+)", text, re.IGNORECASE)
        if name_match:
            facts.append(f"Name: {name_match.group(1).title()}")

        # Interest disclosures: "I like cricket", "mujhe cricket pasand hai", "interested in ..."
        like_match = re.search(r"(?:i like|mujhe|interested in)\s+([^.,!?]+)", text, re.IGNORECASE)
        if like_match:
            facts.append(f"Likes/Interest: {like_match.group(1).strip().title()}")


        return facts

    def _infer_topic(self, turn: ConversationTurn, previous_topic: Optional[str]) -> Optional[str]:
        """Simple deterministic topic extractor from query keywords."""
        lower = turn.transcript.lower()
        if "ai" in lower or "artificial intelligence" in lower:
            return "Artificial Intelligence"
        if "cloud computing" in lower or "cloud" in lower:
            return "Cloud Computing"
        if "machine learning" in lower or "ml" in lower:
            return "Machine Learning"
        if "shah rukh khan" in lower or "srk" in lower:
            return "Shah Rukh Khan"
        if "cricket" in lower:
            return "Cricket"
        # If follow-up question without explicit subject, preserve previous topic
        return previous_topic

    async def update_context_and_snapshot(
        self,
        turn: ConversationTurn,
    ) -> ContextSnapshot:
        """
        Updates active room context with the newly finalized ConversationTurn,
        updates speaker profiles, and produces an immutable ContextSnapshot.
        
        CRITICAL ARCHITECTURAL GUARANTEE:
        Must be invoked BEFORE ResponseEligibility so eligibility can inspect
        previous room turns (e.g. for multi-user follow-up queries).
        """
        async with self._lock:
            room = self._get_or_create_room(turn.room_id)
            room.sequence += 1
            room.active_speaker_id = turn.participant_identity

            # Capture previous turn before appending current turn
            previous_turn = room.recent_turns[-1] if room.recent_turns else None

            # Update topic
            room.current_topic = self._infer_topic(turn, room.current_topic)

            # Speaker Profile Management (strictly isolated by participant_identity)
            speaker_id = turn.participant_identity
            if speaker_id not in room.speaker_profiles:
                room.speaker_profiles[speaker_id] = SpeakerProfile(
                    participant_id=speaker_id,
                    name=turn.participant_display_name,
                    facts=[],
                )

            speaker_profile = room.speaker_profiles[speaker_id]
            speaker_profile.last_active = turn.ended_at
            # Extract and store speaker-specific facts
            new_facts = self._extract_simple_facts(turn.transcript)
            for f in new_facts:
                if f not in speaker_profile.facts:
                    speaker_profile.facts.append(f)

            # Append current turn to recent_turns
            room.recent_turns.append(turn)

            # Bounded window truncation (FIFO)
            if len(room.recent_turns) > self.max_turns:
                room.recent_turns = room.recent_turns[-self.max_turns:]

            snapshot = ContextSnapshot(
                snapshot_id=f"snap-{uuid.uuid4().hex[:12]}",
                room_id=turn.room_id,
                previous_turn=previous_turn,
                recent_turns=list(room.recent_turns),
                current_topic=room.current_topic,
                active_speaker_id=room.active_speaker_id,
                speaker_profile=speaker_profile.model_copy(deep=True),
                all_speaker_profiles={
                    pid: prof.model_copy(deep=True)
                    for pid, prof in room.speaker_profiles.items()
                },
                turn_count=len(room.recent_turns),
                created_at=datetime.now(timezone.utc),
            )

            logger.info(
                f"Room context updated ({turn.room_id}): turn {turn.sequence}, turns in context={len(room.recent_turns)}",
                extra={
                    "room_id": turn.room_id,
                    "speaker_id": turn.participant_identity,
                    "topic": room.current_topic,
                }
            )

            return snapshot

    async def add_turn(self, turn: ConversationTurn) -> ContextSnapshot:
        """Alias for update_context_and_snapshot."""
        return await self.update_context_and_snapshot(turn)

    async def get_context_snapshot(self, room_id: str) -> ContextSnapshot:
        """Retrieves read-only snapshot of current room context."""
        async with self._lock:
            room = self._get_or_create_room(room_id)
            prev_turn = room.recent_turns[-1] if room.recent_turns else None
            return ContextSnapshot(
                snapshot_id=f"snap-{uuid.uuid4().hex[:12]}",
                room_id=room_id,
                previous_turn=prev_turn,
                recent_turns=list(room.recent_turns),
                current_topic=room.current_topic,
                active_speaker_id=room.active_speaker_id,
                speaker_profile=room.speaker_profiles.get(room.active_speaker_id) if room.active_speaker_id else None,
                all_speaker_profiles={
                    pid: prof.model_copy(deep=True)
                    for pid, prof in room.speaker_profiles.items()
                },
                turn_count=len(room.recent_turns),
                created_at=datetime.now(timezone.utc),
            )

    def reset_room(self, room_id: str) -> None:
        """Flushes in-memory room context."""
        self._rooms.pop(room_id, None)


# Global context manager singleton
conversation_context_manager = ConversationContextManager()
