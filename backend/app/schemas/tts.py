"""
Phase 3D: Strongly typed contracts for TTS Request/Response/Events.

Audio format verified:
- Sarvam Bulbul v3 with output_audio_codec='linear16', speech_sample_rate=24000
- Response: AudioOutput.data.audio = base64-encoded raw 16-bit PCM mono
- LiveKit: AudioFrame(data, sample_rate=24000, num_channels=1, samples_per_channel=N)
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class TTSStatus(str, Enum):
    """Lifecycle status of a TTS synthesis request."""
    PENDING = "PENDING"
    STREAMING = "STREAMING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class TTSErrorCategory(str, Enum):
    """Classification of TTS failure reasons."""
    AUTHENTICATION = "AUTHENTICATION"      # Invalid/missing API key
    INVALID_SPEAKER = "INVALID_SPEAKER"    # Speaker ID not found
    INVALID_MODEL = "INVALID_MODEL"        # Model not recognized
    RATE_LIMIT = "RATE_LIMIT"              # 429 / quota exceeded
    TIMEOUT = "TIMEOUT"                    # Request timed out
    WEBSOCKET_DISCONNECT = "WEBSOCKET_DISCONNECT"
    AUDIO_DECODE_ERROR = "AUDIO_DECODE_ERROR"
    LIVEKIT_PUBLISH_ERROR = "LIVEKIT_PUBLISH_ERROR"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class TTSRequest(BaseModel):
    """
    Canonical TTS synthesis request.
    Contains only the text and routing metadata needed for TTS.
    Never includes LLM provider metadata, routing decisions, or JSON wrappers.
    """
    request_id: str = Field(..., description="Unique TTS request UUID (NOT the LLM request_id)")
    turn_id: str = Field(..., description="Associated conversation turn identifier")
    agent_id: str = Field(..., description="Selected AI agent: 'dost' or 'sathi'")
    text: str = Field(..., description="Canonical validated AI response text to synthesize")
    speaker: str = Field(..., description="Sarvam Bulbul v3 speaker voice ID")
    language_code: str = Field(default="hi-IN", description="BCP-47 language code")
    model: str = Field(default="bulbul:v3", description="Sarvam TTS model")
    room_id: str = Field(..., description="LiveKit room name for audio publication")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TTSMetrics(BaseModel):
    """
    Measured TTS performance metrics.
    All values are None if not yet available.
    Do not invent or estimate values — only record observed measurements.
    """
    request_id: str
    turn_id: str
    agent_id: str
    speaker: str
    model: str
    language_code: str

    # Timing (Unix timestamps, seconds precision)
    tts_request_start: Optional[float] = None    # time.perf_counter() when request began
    tts_first_audio_at: Optional[float] = None   # time.perf_counter() at first audio chunk
    tts_completion_at: Optional[float] = None    # time.perf_counter() at final chunk

    # Derived latency values (computed, not stored independently)
    @property
    def time_to_first_audio_ms(self) -> Optional[float]:
        """TTS TTFA: milliseconds from request start to first audio chunk."""
        if self.tts_request_start and self.tts_first_audio_at:
            return round((self.tts_first_audio_at - self.tts_request_start) * 1000.0, 2)
        return None

    @property
    def tts_total_ms(self) -> Optional[float]:
        """Total TTS generation time in milliseconds."""
        if self.tts_request_start and self.tts_completion_at:
            return round((self.tts_completion_at - self.tts_request_start) * 1000.0, 2)
        return None

    # Audio output info
    total_chunks: int = 0
    total_bytes: int = 0
    status: TTSStatus = TTSStatus.PENDING


class TTSCompletedEvent(BaseModel):
    """Event emitted when TTS synthesis and publication completes successfully."""
    event_type: str = "tts.completed"
    request_id: str
    turn_id: str
    agent_id: str
    speaker: str
    model: str
    language_code: str
    time_to_first_audio_ms: Optional[float] = None
    tts_total_ms: Optional[float] = None
    total_chunks: int = 0
    total_bytes: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TTSFailedEvent(BaseModel):
    """Event emitted when TTS synthesis fails."""
    event_type: str = "tts.error"
    request_id: str
    turn_id: str
    agent_id: str
    error_category: TTSErrorCategory
    error_message: str
    is_retryable: bool = False
    # NOTE: TTS failure does NOT trigger new LLM generation.
    # The canonical text is still valid; only synthesis failed.
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TTSCancelledEvent(BaseModel):
    """Event emitted when TTS is cancelled (e.g. barge-in)."""
    event_type: str = "tts.cancelled"
    request_id: str
    turn_id: str
    agent_id: str
    cancellation_reason: str = "barge_in"
    chunks_published: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
