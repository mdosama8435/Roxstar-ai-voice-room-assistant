from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


class ParticipantRole(str, Enum):
    HUMAN = "HUMAN"
    AI_AGENT = "AI_AGENT"


class MediaState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    SPEAKING = "SPEAKING"
    MUTED = "MUTED"
    THINKING = "THINKING"
    CONNECTING = "CONNECTING"
    DISCONNECTED = "DISCONNECTED"


class LanguageCode(str, Enum):
    HINDI = "hi"
    ENGLISH = "en"
    HINGLISH = "hi-Latn"
    AUTO = "auto"


class Participant(BaseModel):
    """
    Represents a participant in a LiveKit voice room, whether human or AI agent.
    """
    id: str = Field(..., description="Unique participant identity (e.g. user_rahul or agent_dost)")
    name: str = Field(..., description="Display name of the participant")
    role: ParticipantRole = Field(..., description="Role distinguishing humans from AI agents")
    persona_id: Optional[str] = Field(None, description="Persona key if AI agent (e.g., 'dost' or 'sathi')")
    gender: Optional[str] = Field(None, description="Gender description (e.g., male, female)")
    media_state: MediaState = Field(default=MediaState.IDLE, description="Current audio/interaction state")
    is_muted: bool = Field(default=False, description="Whether microphone/audio is muted")
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoomState(str, Enum):
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class Room(BaseModel):
    """
    Represents a LiveKit voice room session.
    """
    id: str = Field(..., description="Unique room identifier (e.g. room-demo-roxstar)")
    name: str = Field(..., description="Human-readable room title")
    state: RoomState = Field(default=RoomState.IDLE, description="Lifecycle state of the room")
    participants: List[Participant] = Field(default_factory=list, description="Currently connected participants")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    max_participants: int = Field(default=10, description="Participant capacity")


class ModalityType(str, Enum):
    VOICE = "VOICE"
    TEXT = "TEXT"


class STTSessionClaims(BaseModel):
    """Claims carried in a signed STT WebSocket session token."""
    room_name: str
    participant_identity: str
    display_name: str
    iat: int
    exp: int


class TranscriptEvent(BaseModel):
    """
    Single speech recognition utterance event.
    Standardized Phase 3A streaming STT contract with backward compatibility.
    """
    event_id: str = Field(..., description="Unique transcript event UUID")
    room_id: str = Field(..., description="Target LiveKit room name")
    participant_identity: str = Field(..., description="Authoritative participant identity (human-...)")
    participant_display_name: str = Field(..., description="Display name for presentation")
    transcript: str = Field(..., description="Utterance text in Hindi/Hinglish/English")
    status: Literal["partial", "final"] = Field(..., description="Interim partial or finalized turn")
    provider: str = Field(default="sarvam", description="STT provider identifier")
    model: str = Field(default="saaras:v3-realtime", description="STT model name")
    detected_language: Optional[str] = Field(default="auto", description="Detected BCP-47 language (e.g. hi-IN, en-IN)")
    language_confidence: Optional[float] = Field(None, description="Language identification confidence")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: Optional[int] = Field(default=0, description="Monotonic sequence number for turn reconstruction")
    latency_ms: Optional[float] = Field(None, description="Measured end-to-end latency in milliseconds")

    # Backwards compatibility helpers
    modality: Optional[ModalityType] = Field(default=ModalityType.VOICE, description="VOICE or TEXT origin")
    language: Optional[LanguageCode] = Field(default=LanguageCode.AUTO, description="LanguageCode enum")
    confidence: Optional[float] = Field(default=None, description="Model confidence score")

    @model_validator(mode="before")
    @classmethod
    def handle_compat_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # event_id <-> id
            if "event_id" not in data and "id" in data:
                data["event_id"] = data["id"]
            elif "id" not in data and "event_id" in data:
                data["id"] = data["event_id"]
            # participant_identity <-> speaker_id
            if "participant_identity" not in data and "speaker_id" in data:
                data["participant_identity"] = data["speaker_id"]
            # participant_display_name <-> speaker_name
            if "participant_display_name" not in data and "speaker_name" in data:
                data["participant_display_name"] = data["speaker_name"]
            # transcript <-> text
            if "transcript" not in data and "text" in data:
                data["transcript"] = data["text"]
            # status <-> is_final
            if "status" not in data:
                if "is_final" in data:
                    data["status"] = "final" if data["is_final"] else "partial"
                else:
                    data["status"] = "final"
        return data

    @property
    def id(self) -> str:
        return self.event_id

    @property
    def speaker_id(self) -> str:
        return self.participant_identity

    @property
    def speaker_name(self) -> str:
        return self.participant_display_name

    @property
    def text(self) -> str:
        return self.transcript

    @property
    def is_final(self) -> bool:
        return self.status == "final"


class TurnState(str, Enum):
    """
    Lifecycle state for an utterance/turn in a voice room.
    Expected flow: IDLE -> SPEAKING -> PAUSED -> SPEAKING -> FINALIZING -> COMPLETE
    """
    IDLE = "IDLE"
    SPEAKING = "SPEAKING"
    PAUSED = "PAUSED"
    FINALIZING = "FINALIZING"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"


class ConversationTurn(BaseModel):
    """
    Strongly typed conversational turn representing human speech or authenticated text.
    Phase 3B unified contract with full backward compatibility.
    """
    turn_id: str = Field(..., description="Unique turn identifier")
    room_id: str = Field(..., description="Target room identifier")
    participant_identity: str = Field(..., description="Authoritative opaque participant identity")
    participant_display_name: str = Field(..., description="Display name for presentation")
    transcript: str = Field(..., description="Utterance transcript text")
    language: Optional[str] = Field(default="auto", description="Detected language code")
    language_confidence: Optional[float] = Field(default=None, description="Language confidence score")
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Turn start UTC timestamp")
    ended_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Turn completion or last update UTC timestamp")
    duration_ms: Optional[float] = Field(default=None, description="Utterance duration in milliseconds")
    sequence: int = Field(default=0, description="Monotonic sequence number within room")
    is_complete: bool = Field(default=False, description="Whether this turn has finalized")
    source: Literal["voice", "text"] = Field(default="voice", description="Origin modality")
    transcript_event_id: Optional[str] = Field(default=None, description="ID of associated STT event")

    @model_validator(mode="before")
    @classmethod
    def handle_compat_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # participant_identity <-> speaker_id
            if "participant_identity" not in data and "speaker_id" in data:
                data["participant_identity"] = data["speaker_id"]
            elif "speaker_id" not in data and "participant_identity" in data:
                data["speaker_id"] = data["participant_identity"]
            # participant_display_name <-> speaker_name
            if "participant_display_name" not in data and "speaker_name" in data:
                data["participant_display_name"] = data["speaker_name"]
            elif "speaker_name" not in data and "participant_display_name" in data:
                data["speaker_name"] = data["participant_display_name"]
            # transcript <-> content
            if "transcript" not in data and "content" in data:
                data["transcript"] = data["content"]
            elif "content" not in data and "transcript" in data:
                data["content"] = data["transcript"]
            # started_at <-> start_time
            if "started_at" not in data and "start_time" in data:
                data["started_at"] = data["start_time"]
            elif "start_time" not in data and "started_at" in data:
                data["start_time"] = data["started_at"]
            # ended_at <-> end_time
            if "ended_at" not in data and "end_time" in data:
                data["ended_at"] = data["end_time"]
            elif "end_time" not in data and "ended_at" in data:
                data["end_time"] = data["ended_at"]
            # source <-> modality
            if "source" not in data and "modality" in data:
                mod = str(data["modality"]).upper()
                data["source"] = "text" if "TEXT" in mod else "voice"
        return data

    @property
    def speaker_id(self) -> str:
        return self.participant_identity

    @property
    def speaker_name(self) -> str:
        return self.participant_display_name

    @property
    def content(self) -> str:
        return self.transcript

    @property
    def start_time(self) -> datetime:
        return self.started_at

    @property
    def end_time(self) -> datetime:
        return self.ended_at

    @property
    def modality(self) -> ModalityType:
        return ModalityType.TEXT if self.source == "text" else ModalityType.VOICE


class TriggerType(str, Enum):
    """Categorization of turn intent for response eligibility."""
    DIRECT_QUESTION = "DIRECT_QUESTION"
    DIRECT_REQUEST = "DIRECT_REQUEST"
    FOLLOW_UP = "FOLLOW_UP"
    EXPLICIT_BOT_ADDRESS = "EXPLICIT_BOT_ADDRESS"
    CONTEXTUAL_REQUEST = "CONTEXTUAL_REQUEST"
    CASUAL_STATEMENT = "CASUAL_STATEMENT"
    INCOMPLETE_UTTERANCE = "INCOMPLETE_UTTERANCE"
    ACKNOWLEDGEMENT = "ACKNOWLEDGEMENT"
    SELF_TALK = "SELF_TALK"
    UNKNOWN = "UNKNOWN"


class ResponseEligibility(BaseModel):
    """
    Deterministic response eligibility classification result for a ConversationTurn.
    """
    should_respond: bool = Field(..., description="Whether an AI agent should consider responding")
    reason: str = Field(..., description="Eligibility justification (e.g. explicit_question, acknowledgement)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence score")
    trigger_type: TriggerType = Field(..., description="Classified intent trigger type")
    evidence: Dict[str, Any] = Field(default_factory=dict, description="Extracted heuristic cues or matched tokens")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BotType(str, Enum):
    """Supported bot targets for arbitration."""
    DOST = "DOST"
    SATHI = "SATHI"
    NONE = "NONE"


class BotRoutingDecision(BaseModel):
    """
    Arbitration decision routing a turn to exactly one bot, or silence.
    """
    decision_id: str = Field(..., description="Unique routing decision UUID")
    room_id: str = Field(..., description="Target LiveKit room name")
    turn_id: str = Field(..., description="Associated ConversationTurn identifier")
    selected_bot: BotType = Field(..., description="Chosen bot persona: DOST, SATHI, or NONE")
    reason: str = Field(..., description="Deterministic arbitration rationale")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Routing confidence")
    routing_source: Literal["explicit_rule", "semantic_rule", "fallback"] = Field(
        ..., description="Deterministic decision layer that made the choice"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OrchestrationDecision(BaseModel):
    """
    Final output contract of Phase 3B orchestration layer.
    """
    decision_id: str = Field(..., description="Unique orchestration decision identifier")
    room_id: str = Field(..., description="Target LiveKit room identifier")
    turn_id: str = Field(..., description="Associated turn identifier")
    eligibility: ResponseEligibility = Field(..., description="Response eligibility evaluation")
    routing: BotRoutingDecision = Field(..., description="Single-bot routing decision")
    context_snapshot_id: Optional[str] = Field(None, description="ID of room context snapshot at decision time")
    turn_lock_acquired: bool = Field(default=False, description="Whether room audio lock was acquired")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OrchestrationEventType(str, Enum):
    TURN_STARTED = "TURN_STARTED"
    TURN_PAUSED = "TURN_PAUSED"
    TURN_RESUMED = "TURN_RESUMED"
    TURN_COMPLETED = "TURN_COMPLETED"
    RESPONSE_ELIGIBILITY_EVALUATED = "RESPONSE_ELIGIBILITY_EVALUATED"
    BOT_ROUTING_DECIDED = "BOT_ROUTING_DECIDED"
    TURN_LOCK_ACQUIRED = "TURN_LOCK_ACQUIRED"
    TURN_LOCK_BLOCKED = "TURN_LOCK_BLOCKED"
    TURN_LOCK_RELEASED = "TURN_LOCK_RELEASED"
    CONTEXT_UPDATED = "CONTEXT_UPDATED"
    ORCHESTRATION_DECISION = "ORCHESTRATION_DECISION"
    LLM_REQUEST_STARTED = "LLM_REQUEST_STARTED"
    LLM_FIRST_TOKEN = "LLM_FIRST_TOKEN"
    LLM_STREAM_CHUNK = "LLM_STREAM_CHUNK"
    LLM_RESPONSE_COMPLETED = "LLM_RESPONSE_COMPLETED"
    LLM_RESPONSE_FAILED = "LLM_RESPONSE_FAILED"
    LLM_CANCELLED = "LLM_CANCELLED"


class OrchestrationEvent(BaseModel):
    """
    Structured orchestration event for observability and room broadcast.
    """
    event_id: str = Field(..., description="Unique event UUID")
    event_type: OrchestrationEventType = Field(..., description="Event lifecycle identifier")
    room_id: str = Field(..., description="Associated LiveKit room identifier")
    participant_identity: Optional[str] = Field(None, description="Associated participant identity")
    turn_id: Optional[str] = Field(None, description="Associated turn identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event data payload")


class RoutingDecisionType(str, Enum):
    SPEAK = "SPEAK"
    SILENCE = "SILENCE"


class AgentDecision(BaseModel):
    """
    Arbitration decision specifying which AI agent speaks, or if silence is maintained.
    """
    turn_id: str = Field(..., description="ID of the triggering turn")
    room_id: str = Field(..., description="Target room identifier")
    decision_type: RoutingDecisionType = Field(..., description="SPEAK or SILENCE")
    selected_agent: Optional[str] = Field(None, description="'dost', 'sathi', or None if silence")
    reason: str = Field(..., description="Arbitration rationale (e.g., 'Addressed directly', 'SILENCE: human-to-human banter')")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Router confidence score")
    source: str = Field(default="bot_router", description="Arbitration component identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SpeakerProfile(BaseModel):
    """
    Persistent profile and remembered facts for a human participant.
    """
    participant_id: str = Field(..., description="Unique participant identity")
    name: str = Field(..., description="Participant display name")
    preferred_language: LanguageCode = Field(default=LanguageCode.AUTO)
    language_style: str = Field(default="conversational_hinglish", description="Linguistic style pattern")
    facts: List[str] = Field(default_factory=list, description="Extracted speaker-specific facts")
    first_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoomContext(BaseModel):
    """
    Shared room context unifying active speaker, topic, and recent dialogue turns.
    """
    room_id: str = Field(..., description="Target room identifier")
    current_topic: Optional[str] = Field(None, description="Inferred active topic")
    active_speaker_id: Optional[str] = Field(None, description="Participant ID currently speaking")
    current_agent_id: Optional[str] = Field(None, description="Active AI agent in conversation")
    language_style: str = Field(default="conversational_hinglish")
    recent_turns: List[ConversationTurn] = Field(default_factory=list)
    speaker_profiles: Dict[str, SpeakerProfile] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PipelineStage(str, Enum):
    LIVEKIT = "LIVEKIT"
    STT = "STT"
    TURN_DETECTION = "TURN_DETECTION"
    ROUTER = "ROUTER"
    MEMORY = "MEMORY"
    LLM = "LLM"
    TTS = "TTS"


class PipelineEvent(BaseModel):
    """
    Lifecycle telemetry event tracking progress through the AI voice pipeline.
    """
    event_id: str = Field(..., description="Unique event identifier")
    room_id: str = Field(..., description="Target room identifier")
    stage: PipelineStage = Field(..., description="Pipeline stage executing")
    status: str = Field(..., description="'started', 'completed', 'failed', 'cancelled'")
    participant_id: Optional[str] = Field(None)
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LatencyMetric(BaseModel):
    """
    Latency breakdown for a single voice-to-voice turn.
    """
    turn_id: str = Field(..., description="Associated turn identifier")
    room_id: str = Field(..., description="Target room identifier")
    stt_duration_ms: Optional[float] = Field(None, description="Audio end to transcript ready (ms)")
    router_duration_ms: Optional[float] = Field(None, description="Router arbitration time (ms)")
    llm_ttft_ms: Optional[float] = Field(None, description="Time to first LLM token (ms)")
    llm_total_ms: Optional[float] = Field(None, description="Total LLM generation duration (ms)")
    tts_first_chunk_ms: Optional[float] = Field(None, description="Text input to first audio chunk (ms)")
    total_e2e_ms: Optional[float] = Field(None, description="Human speech end to bot audio heard (ms)")
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoomSummary(BaseModel):
    """
    Bonus: Rolling summary model for long-running room conversations.
    """
    room_id: str
    summary: str
    key_decisions: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ContentModerationFlag(BaseModel):
    """
    Bonus: Moderation flag contract.
    """
    flag_id: str
    room_id: str
    speaker_id: str
    flag_type: str
    severity: str
    snippet: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LiveKitTokenRequest(BaseModel):
    """
    Request model for generating a LiveKit room access token.
    Enforces strict input validation on room name and display name.
    """
    room_name: str = Field(
        ...,
        min_length=2,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="Target LiveKit room name (alphanumeric, underscores, hyphens)"
    )
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="User display name (e.g. 'Rahul', 'Priya')"
    )
    participant_identity: Optional[str] = Field(
        None,
        max_length=128,
        description="Optional pre-generated opaque identity (e.g. 'human-...') without PII"
    )


class LiveKitTokenResponse(BaseModel):
    """
    Response model containing signed LiveKit access token and connection parameters.
    """
    server_url: str = Field(..., description="LiveKit server WebSocket URL")
    token: str = Field(..., description="Signed LiveKit JWT access token")
    room_name: str = Field(..., description="Target room identifier")
    participant_identity: str = Field(..., description="Opaque unique participant identifier")
    display_name: str = Field(..., description="Sanitized participant display name")
    stt_token: Optional[str] = Field(None, description="Cryptographically signed STT WebSocket session token")


class LiveKitDataChatMessage(BaseModel):
    """
    Payload schema for typed chat messages sent over LiveKit DataChannel.
    """
    type: str = Field(default="chat.message", description="Message type identifier")
    message_id: str = Field(..., description="Unique message identifier")
    sender_id: str = Field(..., description="Opaque sender LiveKit participant identity")
    sender_name: str = Field(..., description="Display name of sender")
    text: str = Field(..., min_length=1, max_length=2000, description="Chat message body")
    timestamp: str = Field(..., description="ISO 8601 formatted timestamp")
    version: int = Field(default=1, description="Data contract version")


class LiveKitTranscriptDataMessage(BaseModel):
    """
    Payload schema for broadcasted final transcripts sent over LiveKit DataChannel.
    Topic: 'transcript.stream'
    """
    type: str = Field(default="transcript.event", description="Message type identifier")
    event_id: str = Field(..., description="Unique transcript event identifier")
    room_name: str = Field(..., description="Target LiveKit room name")
    participant_identity: str = Field(..., description="Opaque speaker LiveKit participant identity")
    participant_display_name: str = Field(..., description="Display name of speaker")
    transcript: str = Field(..., description="Transcribed text in Hindi, English, or Hinglish")
    status: str = Field(default="final", description="'partial' or 'final'")
    detected_language: str = Field(default="auto", description="Detected language label or code")
    language_confidence: Optional[float] = Field(None, description="Language detection confidence score")
    latency_ms: Optional[float] = Field(None, description="End-to-end STT latency in milliseconds")
    sequence: int = Field(default=0, description="Monotonic sequence number for turn order")
    timestamp: str = Field(..., description="ISO 8601 formatted timestamp")
    version: int = Field(default=1, description="Data contract version")


class LiveKitOrchestrationDataMessage(BaseModel):
    """
    Payload schema for broadcasted orchestration decisions sent over LiveKit DataChannel.
    Topic: 'orchestration.stream'
    """
    type: str = Field(default="orchestration.event", description="Message type identifier")
    event_id: str = Field(..., description="Unique orchestration event identifier")
    room_name: str = Field(..., description="Target LiveKit room name")
    turn_id: str = Field(..., description="Associated turn identifier")
    participant_identity: str = Field(..., description="Speaker LiveKit participant identity")
    participant_display_name: str = Field(..., description="Display name of speaker")
    transcript: str = Field(..., description="Utterance text")
    should_respond: bool = Field(..., description="Whether response is required")
    trigger_type: str = Field(..., description="Intent trigger type")
    selected_bot: str = Field(..., description="DOST, SATHI, or NONE")
    routing_reason: str = Field(..., description="Arbitration reason")
    turn_lock_acquired: bool = Field(..., description="Whether audio response lock was acquired")
    lock_deferred: bool = Field(default=False, description="Whether response is deferred due to active lock")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Pipeline latency metrics")
    timestamp: str = Field(..., description="ISO 8601 formatted timestamp")
    version: int = Field(default=1, description="Data contract version")

