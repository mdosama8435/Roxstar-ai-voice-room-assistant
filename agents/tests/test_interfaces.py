from typing import AsyncIterator, List
from agents.app.speech.interfaces import (
    SpeechToTextProvider,
    TextToSpeechProvider,
    STTTranscriptResult,
)
from agents.app.orchestration.interfaces import (
    BotRouter,
    TurnDetector,
    TurnLockManager,
    LanguageModelProvider,
)
from agents.app.memory.interfaces import MemoryProvider
from backend.app.schemas.contracts import (
    AgentDecision,
    ConversationTurn,
    RoomContext,
    SpeakerProfile,
)


class DummySTT:
    async def connect(self, room_name: str, participant_identity: str, participant_name: str) -> None:
        pass

    async def push_audio_chunk(self, pcm_bytes: bytes) -> None:
        pass

    async def receive_events(self) -> AsyncIterator[STTTranscriptResult]:
        yield STTTranscriptResult(text="", is_final=True, detected_language="hi-IN")

    async def flush(self) -> None:
        pass

    async def close(self) -> None:
        pass


class DummyTTS:
    """Stub matching Phase 3D TextToSpeechProvider protocol (tests only)."""

    async def synthesize_stream(
        self,
        text_chunks: AsyncIterator[str],
        speaker: str,
        request_id: str,
        turn_id: str,
        agent_id: str,
    ) -> AsyncIterator[bytes]:
        yield b""

    def cancel_request(self, request_id: str) -> None:
        pass

    async def close(self) -> None:
        pass


class DummyRouter:
    async def arbitrate(
        self,
        incoming_turn: ConversationTurn,
        room_context: RoomContext,
    ) -> AgentDecision:
        raise NotImplementedError


class DummyMemory:
    async def get_room_context(self, room_id: str) -> RoomContext:
        raise NotImplementedError

    async def append_turn(self, room_id: str, turn: ConversationTurn) -> None:
        pass

    async def get_speaker_profile(self, participant_id: str) -> SpeakerProfile:
        raise NotImplementedError

    async def save_speaker_fact(self, participant_id: str, fact: str) -> None:
        pass

    async def truncate_context(self, room_id: str, max_turns: int = 15) -> None:
        pass


def test_protocol_compliance():
    """Verify concrete classes can satisfy the runtime_checkable protocol boundaries."""
    assert isinstance(DummySTT(), SpeechToTextProvider)
    assert isinstance(DummyTTS(), TextToSpeechProvider)
    assert isinstance(DummyRouter(), BotRouter)
    assert isinstance(DummyMemory(), MemoryProvider)
