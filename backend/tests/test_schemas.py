from datetime import datetime, timezone
from app.schemas.contracts import (
    ParticipantRole,
    MediaState,
    LanguageCode,
    Participant,
    RoomState,
    Room,
    ModalityType,
    TranscriptEvent,
    ConversationTurn,
    RoutingDecisionType,
    AgentDecision,
    SpeakerProfile,
    RoomContext,
    PipelineStage,
    PipelineEvent,
    LatencyMetric,
)


def test_participant_and_room_contracts():
    p1 = Participant(
        id="user_rahul",
        name="Rahul",
        role=ParticipantRole.HUMAN,
        media_state=MediaState.IDLE,
    )
    p2 = Participant(
        id="agent_dost",
        name="AI Dost",
        role=ParticipantRole.AI_AGENT,
        persona_id="dost",
        gender="male",
        media_state=MediaState.IDLE,
    )
    room = Room(
        id="room-demo-roxstar",
        name="Demo Voice Room",
        state=RoomState.ACTIVE,
        participants=[p1, p2],
    )
    assert len(room.participants) == 2
    assert room.participants[0].name == "Rahul"
    assert room.participants[1].role == ParticipantRole.AI_AGENT


def test_agent_decision_contract_supports_silence():
    decision_silence = AgentDecision(
        turn_id="turn_123",
        room_id="room-demo-roxstar",
        decision_type=RoutingDecisionType.SILENCE,
        selected_agent=None,
        reason="Human to human banter; no AI summon detected",
        confidence=0.95,
        source="bot_router",
    )
    assert decision_silence.decision_type == RoutingDecisionType.SILENCE
    assert decision_silence.selected_agent is None

    decision_speak = AgentDecision(
        turn_id="turn_124",
        room_id="room-demo-roxstar",
        decision_type=RoutingDecisionType.SPEAK,
        selected_agent="dost",
        reason="Direct mention 'Dost'",
        confidence=0.98,
        source="bot_router",
    )
    assert decision_speak.decision_type == RoutingDecisionType.SPEAK
    assert decision_speak.selected_agent == "dost"


def test_transcript_and_speaker_profile():
    transcript = TranscriptEvent(
        id="evt_001",
        room_id="room-demo-roxstar",
        speaker_id="user_rahul",
        speaker_name="Rahul",
        modality=ModalityType.VOICE,
        text="Namaste Dost, kaise ho?",
        language=LanguageCode.HINGLISH,
        is_final=True,
        confidence=0.94,
    )
    assert transcript.language == LanguageCode.HINGLISH
    assert transcript.text.startswith("Namaste")

    profile = SpeakerProfile(
        participant_id="user_rahul",
        name="Rahul",
        preferred_language=LanguageCode.HINGLISH,
        facts=["Prefers brief answers", "Speaks Hinglish"],
    )
    assert len(profile.facts) == 2
