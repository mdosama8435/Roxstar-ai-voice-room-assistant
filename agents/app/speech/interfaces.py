from typing import Any, AsyncIterator, Dict, Optional, Protocol, runtime_checkable
from pydantic import BaseModel, Field, model_validator


class SarvamSaarasConfig(BaseModel):
    """Configuration for Sarvam Saaras streaming STT."""
    model_name: str = "saaras:v3-realtime"
    language_code: str = "auto"
    sample_rate: int = 16000
    channels: int = 1
    chunk_duration_ms: int = 100


class SarvamBulbulConfig(BaseModel):
    """Configuration for Sarvam Bulbul v3 streaming TTS.

    Verified from sarvamai SDK (v0.1.34) configure() source:
    - model: 'bulbul:v3' (NOT 'bulbul-v3')
    - speaker: real voice IDs from SDK configure() parameter docs
    - output_audio_codec: 'linear16' supported (verified from ConfigureConnectionDataOutputAudioCodec type)
    - speech_sample_rate: 24000 Hz default for bulbul:v3
    - bulbul:v3 does NOT support pitch or loudness (pace and temperature only)
    """
    model_name: str = "bulbul:v3"
    # Verified speaker IDs from SDK source:
    # configure() param docs list: Female: Anushka, Manisha, Vidya, Arya; Male: Abhilash, Karun, Hitesh
    # shubh = Dost (male); priya = Sathi (female, live-verified for bulbul:v3)
    voice_male: str = "shubh"
    voice_female: str = "priya"
    # pace range: 0.5-2.0 (bulbul:v3 does NOT support pitch/loudness)
    pace: float = 1.0
    # temperature: bulbul:v3 only
    temperature: float = 0.6
    # Verified: linear16 is in ConfigureConnectionDataOutputAudioCodec union type
    output_audio_codec: str = "linear16"
    # 24000 Hz is bulbul:v3 default; supported: 8000, 16000, 22050, 24000
    speech_sample_rate: int = 24000


class STTTranscriptResult(BaseModel):
    """Transcript event emitted by an STT provider."""
    text: str
    is_final: bool
    detected_language: Optional[str] = "auto"
    language_confidence: Optional[float] = None
    latency_ms: Optional[float] = None
    raw_event: Optional[Dict[str, Any]] = None

    @model_validator(mode="before")
    @classmethod
    def handle_compat(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "language" in data and "detected_language" not in data:
                data["detected_language"] = data["language"]
            if "confidence" in data and "language_confidence" not in data:
                data["language_confidence"] = data["confidence"]
        return data

    @property
    def language(self) -> str:
        return self.detected_language or "auto"

    @property
    def confidence(self) -> Optional[float]:
        return self.language_confidence


@runtime_checkable
class SpeechToTextProvider(Protocol):
    """
    Abstract interface for streaming Speech-to-Text providers (e.g. Sarvam Saaras).
    """
    async def connect(self, room_name: str, participant_identity: str, participant_name: str) -> None:
        """Establish streaming session with STT provider bound to participant."""
        ...

    async def push_audio_chunk(self, pcm_bytes: bytes) -> None:
        """Push raw 16kHz S16LE PCM chunk to the STT engine."""
        ...

    async def receive_events(self) -> AsyncIterator[STTTranscriptResult]:
        """Yield real-time transcript results."""
        ...

    async def flush(self) -> None:
        """Flush in-flight audio buffers."""
        ...

    async def close(self) -> None:
        """Gracefully terminate STT stream."""
        ...


@runtime_checkable
class TextToSpeechProvider(Protocol):
    """
    Abstract interface for streaming Text-to-Speech providers (Sarvam Bulbul v3).

    Implementations yield VerifiedPCMChunk (preferred) or raw PCM bytes.
    Audio format is validated at the Sarvam → LiveKit boundary (pcm_format.py).
    """
    async def synthesize_stream(
        self,
        text_chunks: AsyncIterator[str],
        speaker: str,
        request_id: str,
        turn_id: str,
        agent_id: str,
    ) -> AsyncIterator[Any]:
        """Convert chunked text into validated PCM audio chunks via Sarvam Bulbul v3."""
        ...

    def cancel_request(self, request_id: str) -> None:
        """Signal cancellation for active TTS request (request-scoped, safe for barge-in)."""
        ...

    async def close(self) -> None:
        """Clean up TTS resources."""
        ...
