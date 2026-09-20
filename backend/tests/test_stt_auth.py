import time
import pytest
from app.config import settings
from app.services.stt_auth import (
    generate_stt_token,
    verify_stt_token,
    verify_stt_token_claims,
)


def test_stt_token_generation_and_verification():
    room = "test-room-1"
    identity = "human-rahul-01"
    name = "Rahul Sharma"

    token = generate_stt_token(room_name=room, participant_identity=identity, display_name=name)
    assert token is not None
    assert "." in token

    is_valid, claims, reason = verify_stt_token(token)
    assert is_valid is True
    assert reason is None
    assert claims["room_name"] == room
    assert claims["participant_identity"] == identity
    assert claims["display_name"] == name
    assert claims["exp"] > claims["iat"]

    # Test strongly-typed claims
    typed_claims = verify_stt_token_claims(token)
    assert typed_claims.room_name == room
    assert typed_claims.participant_identity == identity
    assert typed_claims.display_name == name


def test_stt_token_tampering_rejected():
    room = "test-room-2"
    identity = "human-priya-02"

    token = generate_stt_token(room_name=room, participant_identity=identity)
    parts = token.split(".")
    assert len(parts) == 2

    # Tamper with signature
    tampered_sig = parts[1][:-2] + ("ab" if parts[1][-2:] != "ab" else "cd")
    tampered_token = f"{parts[0]}.{tampered_sig}"

    is_valid, claims, reason = verify_stt_token(tampered_token)
    assert is_valid is False
    assert claims is None
    assert "signature" in reason.lower()

    with pytest.raises(ValueError, match="signature"):
        verify_stt_token_claims(tampered_token)


def test_stt_token_expiration_rejected():
    room = "test-room-3"
    identity = "human-expired-03"

    # Issue token with negative expiry
    token = generate_stt_token(room_name=room, participant_identity=identity, expiry_minutes=-5)

    is_valid, claims, reason = verify_stt_token(token)
    assert is_valid is False
    assert claims is None
    assert "expired" in reason.lower()

    with pytest.raises(ValueError, match="expired"):
        verify_stt_token_claims(token)


def test_stt_token_identity_and_room_mismatch():
    token = generate_stt_token(
        room_name="room-alpha",
        participant_identity="human-user-123",
        display_name="User Alpha"
    )

    # Valid with correct expectations
    is_valid, claims, _ = verify_stt_token(token, expected_room_name="room-alpha", expected_participant_identity="human-user-123")
    assert is_valid is True

    # Room mismatch
    is_valid, claims, reason = verify_stt_token(token, expected_room_name="room-beta")
    assert is_valid is False
    assert "room" in reason.lower()

    # Identity mismatch (prevent identity spoofing)
    is_valid, claims, reason = verify_stt_token(token, expected_participant_identity="human-impostor")
    assert is_valid is False
    assert "identity" in reason.lower()


def test_stt_token_malformed_formats():
    assert verify_stt_token("")[0] is False
    assert verify_stt_token("no-dots-here")[0] is False
    assert verify_stt_token("a.b.c")[0] is False
    assert verify_stt_token("invalid_payload.invalid_sig")[0] is False
