"""
Strongly typed contracts and schemas for Phase 3C LLM Response Generation.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.contracts import BotType


class LLMStatus(str, Enum):
    """Execution status of an LLM generation lifecycle."""
    IDLE = "IDLE"
    STANDBY = "STANDBY"
    REQUESTING = "REQUESTING"
    STREAMING = "STREAMING"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class LLMRequest(BaseModel):
    """
    Standardized vendor-agnostic request contract dispatched to LLMProvider.
    """
    request_id: str = Field(..., description="Unique generation request UUID")
    room_id: str = Field(..., description="Target LiveKit room name")
    participant_identity: str = Field(..., description="Originating participant identity")
    selected_bot: BotType = Field(..., description="Authoritative bot chosen by Phase 3B router")
    turn_id: str = Field(..., description="Associated conversation turn identifier")
    user_message: str = Field(..., description="Current user utterance text")
    system_prompt: str = Field(..., description="Combined safety, persona, and constraint prompt")
    context_messages: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Structured multi-turn history messages with role and content"
    )
    speaker_profile: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Speaker attributes and language confidence"
    )
    speaker_facts: List[str] = Field(
        default_factory=list,
        description="Known facts extracted for current speaker"
    )
    model: Optional[str] = Field(default=None, description="Optional model override")
    temperature: Optional[float] = Field(default=None, description="Sampling temperature")
    max_tokens: Optional[int] = Field(default=None, description="Maximum tokens to generate")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LLMResponse(BaseModel):
    """
    Completed response contract returned from LLMProvider.
    """
    request_id: str = Field(..., description="Associated request identifier")
    bot: BotType = Field(..., description="Responding bot persona")
    text: str = Field(..., description="Validated response text")
    model: str = Field(..., description="Actual model utilized")
    provider: str = Field(..., description="Provider name (e.g. 'gemini', 'mock')")
    finish_reason: str = Field(default="stop", description="Generation stop reason")
    latency_ms: float = Field(..., description="Total LLM generation latency in milliseconds")
    first_token_latency_ms: Optional[float] = Field(
        default=None,
        description="Time to first token in milliseconds"
    )
    token_count: Optional[int] = Field(default=None, description="Tokens generated if reported")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LLMStreamChunk(BaseModel):
    """
    Incremental text delta chunk yielded during LLM streaming.
    """
    request_id: str = Field(..., description="Associated request identifier")
    bot: BotType = Field(..., description="Responding bot persona")
    text_delta: str = Field(..., description="Incremental text fragment")
    sequence: int = Field(..., description="0-indexed monotonic chunk sequence number")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_final: bool = Field(default=False, description="Whether this is the final stream chunk")


class AIResponseGeneratedEvent(BaseModel):
    """
    Final canonical AI response event produced after validation and lock verification.
    """
    event_id: str = Field(..., description="Unique event identifier")
    request_id: str = Field(..., description="Associated LLM request identifier")
    room_id: str = Field(..., description="Target LiveKit room name")
    bot: BotType = Field(..., description="Responding bot persona (DOST or SATHI)")
    responding_to_turn_id: str = Field(..., description="Human conversation turn responded to")
    text: str = Field(..., description="Final validated spoken text")
    model: str = Field(..., description="Model name")
    provider: str = Field(..., description="Provider name")
    latency_ms: float = Field(..., description="Total pipeline latency from turn completion")
    first_token_latency_ms: Optional[float] = Field(default=None, description="Time to first token")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LiveKitAIResponseDataMessage(BaseModel):
    """
    DataChannel broadcast payload for canonical final AI response.
    Broadcasts on DataChannel topic 'orchestration.stream'.
    """
    type: str = "ai.response"
    event_id: str
    request_id: str
    room_name: str
    bot: str
    bot_display_name: str
    responding_to_turn_id: str
    text: str
    model: str
    latency_ms: float
    timestamp: str


class LiveKitAIResponseChunkMessage(BaseModel):
    """
    DataChannel broadcast payload for ephemeral streaming preview.
    Temporary chunks are displayed in preview only; not persisted as separate chat messages.
    """
    type: str = "ai.response.chunk"
    request_id: str
    room_name: str
    bot: str
    sequence: int
    text_delta: str
    is_final: bool = False
    timestamp: str
