import jwt
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)


def test_token_missing_credentials():
    """Verify HTTP 503 when LiveKit credentials are not configured."""
    original_url = settings.livekit_url
    original_key = settings.livekit_api_key
    original_secret = settings.livekit_api_secret

    try:
        settings.livekit_url = None
        settings.livekit_api_key = None
        settings.livekit_api_secret = None

        response = client.post(
            "/api/v1/livekit/token",
            json={
                "room_name": "room-demo-roxstar",
                "display_name": "Rahul"
            }
        )
        assert response.status_code == 503
        assert "LiveKit is not configured" in response.json()["detail"]
    finally:
        settings.livekit_url = original_url
        settings.livekit_api_key = original_key
        settings.livekit_api_secret = original_secret


def test_token_input_validation_empty_or_invalid():
    """Verify 422/400 on empty room name, invalid characters, or missing display name."""
    # Empty room name (Pydantic min_length=2)
    res1 = client.post("/api/v1/livekit/token", json={"room_name": "", "display_name": "Rahul"})
    assert res1.status_code == 422

    # Invalid room name with special characters (spaces or quotes)
    res2 = client.post("/api/v1/livekit/token", json={"room_name": "bad room!@#", "display_name": "Rahul"})
    assert res2.status_code == 422

    # Missing display name
    res3 = client.post("/api/v1/livekit/token", json={"room_name": "valid-room"})
    assert res3.status_code == 422


def test_token_generation_success_and_claims():
    """Verify successful token generation, opaque identity, and video grants."""
    original_url = settings.livekit_url
    original_key = settings.livekit_api_key
    original_secret = settings.livekit_api_secret

    test_key = "test_dev_livekit_key_0123456789"
    test_secret = "test_dev_livekit_secret_0123456789_abcdef"
    test_url = "wss://test.livekit.cloud"

    try:
        settings.livekit_url = test_url
        settings.livekit_api_key = test_key
        settings.livekit_api_secret = test_secret

        response = client.post(
            "/api/v1/livekit/token",
            json={
                "room_name": "roxstar-test",
                "display_name": "Rahul"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["server_url"] == test_url
        assert data["room_name"] == "roxstar-test"
        assert data["display_name"] == "Rahul"

        # Verify opaque identity: must NOT be "Rahul", must start with "human-"
        participant_id = data["participant_identity"]
        assert participant_id.startswith("human-")
        assert participant_id.lower() != "rahul"

        # Decode JWT without verifying signature to inspect payload claims
        token = data["token"]
        payload = jwt.decode(token, options={"verify_signature": False})
        
        assert payload["iss"] == test_key
        assert payload["sub"] == participant_id
        assert payload["name"] == "Rahul"
        assert "video" in payload
        assert payload["video"]["room"] == "roxstar-test"
        assert payload["video"]["roomJoin"] is True
        assert payload["video"]["canPublish"] is True
        assert payload["video"]["canSubscribe"] is True
        assert payload["video"]["canPublishData"] is True
        assert "exp" in payload
    finally:
        settings.livekit_url = original_url
        settings.livekit_api_key = original_key
        settings.livekit_api_secret = original_secret
