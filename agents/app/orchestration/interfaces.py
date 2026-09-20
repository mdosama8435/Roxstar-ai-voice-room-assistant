from datetime import datetime, timezone
from typing import AsyncIterator, List, Optional, Protocol, runtime_checkable
from pydantic import BaseModel, Field
from backend.app.schemas.contracts import AgentDecision, ConversationTurn, RoomContext


class TurnDetectionResult(BaseModel):
    """Result emitted by turn detector upon detecting speech boundary."""
    is_turn_complete: bool
    speaker_id: str
    transcription_text: str
    silence_duration_ms: float
    confidence: float


class BargeInSignal(BaseModel):
    """Signal emitted when human participant interrupts ongoing bot speech."""
    speaker_id: str
    room_id: str
    audio_energy: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


@runtime_checkable
class TurnDetector(Protocol):
    """
    Protocol for detecting completion of human speech turns and pauses.
    """
    async def process_audio_frame(self, audio_chunk: bytes) -> Optional[TurnDetectionResult]:
        ...

    def reset(self) -> None:
        ...


@runtime_checkable
class BotRouter(Protocol):
    """
    Protocol for arbitrating between Roxstar AI Dost, Roxstar AI Sathi, or Silence.
    Prevents dual-speaking and avoids chiming in on human-to-human dialogues.
    """
    async def arbitrate(
        self,
        incoming_turn: ConversationTurn,
        room_context: RoomContext,
    ) -> AgentDecision:
        ...


@runtime_checkable
class TurnLockManager(Protocol):
    """
    Protocol for managing room audio speech lock to ensure single-speaker mutex.
    """
    async def acquire_lock(self, room_id: str, agent_id: str, ttl_seconds: int = 15) -> bool:
        ...

    async def release_lock(self, room_id: str, agent_id: str) -> None:
        ...

    async def force_unlock_on_barge_in(self, room_id: str) -> None:
        ...


@runtime_checkable
class LanguageModelProvider(Protocol):
    """
    Abstract interface for LLM completion streaming.
    Decoupled from specific LLM providers.
    """
    async def generate_response_stream(
        self,
        system_prompt: str,
        turns: List[ConversationTurn],
        max_tokens: int = 250,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        ...

    async def cancel_generation(self) -> None:
        """Abort in-flight generation stream upon barge-in."""
        ...
