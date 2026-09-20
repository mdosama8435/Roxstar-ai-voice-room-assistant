from agents.app.agents.personas import DOST_PERSONA, SATHI_PERSONA, get_persona
from agents.app.orchestration.interfaces import BargeInSignal, TurnDetectionResult


def test_persona_integrity():
    assert DOST_PERSONA.id == "dost"
    assert DOST_PERSONA.gender == "male"
    # Phase 3D: Sarvam Bulbul v3 speaker IDs (not legacy bulbul-v3-*-hindi placeholders)
    assert DOST_PERSONA.voice_id == "shubh"
    assert "Hindi" in DOST_PERSONA.languages[0]

    assert SATHI_PERSONA.id == "sathi"
    assert SATHI_PERSONA.gender == "female"
    assert SATHI_PERSONA.voice_id == "priya"

    # Check persona resolver
    assert get_persona("dost") is not None
    assert get_persona("sathi") is not None
    assert get_persona("unknown") is None


def test_barge_in_and_turn_detection_models():
    signal = BargeInSignal(
        speaker_id="user_priya",
        room_id="room-demo-roxstar",
        audio_energy=0.82,
    )
    assert signal.speaker_id == "user_priya"
    assert signal.audio_energy > 0.65

    turn_res = TurnDetectionResult(
        is_turn_complete=True,
        speaker_id="user_rahul",
        transcription_text="Sathi, can you help with this?",
        silence_duration_ms=620.0,
        confidence=0.98,
    )
    assert turn_res.is_turn_complete is True
    assert turn_res.silence_duration_ms >= 500.0
