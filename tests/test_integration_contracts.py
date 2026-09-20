"""
Integration contract verification across backend schemas and agent worker protocols.
Ensures data contracts remain harmonized across both domains.
"""
from backend.app.schemas.contracts import (
    Participant,
    ParticipantRole,
    MediaState,
    AgentDecision,
    RoutingDecisionType,
    RoomContext,
    SpeakerProfile,
)
from agents.app.agents.personas import DOST_PERSONA, SATHI_PERSONA, get_persona


def test_persona_and_participant_contract_harmony():
    """Verify agent persona configs map cleanly to Participant schema."""
    dost_config = get_persona("dost")
    assert dost_config is not None

    dost_participant = Participant(
        id=f"agent_{dost_config.id}",
        name=dost_config.name,
        role=ParticipantRole.AI_AGENT,
        persona_id=dost_config.id,
        gender=dost_config.gender,
        media_state=MediaState.IDLE,
    )
    assert dost_participant.role == ParticipantRole.AI_AGENT
    assert dost_participant.persona_id == "dost"


def test_room_context_speaker_profile_mapping():
    """Verify SpeakerProfile aligns with RoomContext schema."""
    context = RoomContext(
        room_id="room-demo-roxstar",
        current_topic="Introductions",
        active_speaker_id="user_rahul",
    )
    profile = SpeakerProfile(
        participant_id="user_rahul",
        name="Rahul",
        facts=["Interested in Audio AI"],
    )
    context.speaker_profiles[profile.participant_id] = profile
    assert "user_rahul" in context.speaker_profiles
    assert len(context.speaker_profiles["user_rahul"].facts) == 1
