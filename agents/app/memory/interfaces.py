from typing import List, Optional, Protocol, runtime_checkable
from backend.app.schemas.contracts import ConversationTurn, RoomContext, SpeakerProfile


@runtime_checkable
class MemoryProvider(Protocol):
    """
    Protocol for room and speaker memory management.
    Separates memory persistence and retrieval from agent persona logic.
    """
    async def get_room_context(self, room_id: str) -> RoomContext:
        ...

    async def append_turn(self, room_id: str, turn: ConversationTurn) -> None:
        ...

    async def get_speaker_profile(self, participant_id: str) -> Optional[SpeakerProfile]:
        ...

    async def save_speaker_fact(self, participant_id: str, fact: str) -> None:
        ...

    async def truncate_context(self, room_id: str, max_turns: int = 15) -> None:
        """Prunes turn history while preserving summarized context."""
        ...


@runtime_checkable
class RedisSessionMemoryInterface(Protocol):
    """
    Interface for short-lived room/session state in Redis.
    """
    async def get_session_turns(self, room_id: str, limit: int = 10) -> List[ConversationTurn]:
        ...

    async def cache_room_state(self, room_id: str, state_json: str, ttl_seconds: int = 3600) -> None:
        ...


@runtime_checkable
class VectorMemoryInterface(Protocol):
    """
    Interface for persistent semantic memory (PostgreSQL + pgvector).
    """
    async def query_relevant_facts(self, participant_id: str, query_text: str, top_k: int = 3) -> List[str]:
        ...

    async def store_embedding(self, participant_id: str, text: str, embedding: List[float]) -> None:
        ...
