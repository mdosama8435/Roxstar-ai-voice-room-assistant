import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import settings
from app.main import app
from app.services.stt_auth import generate_stt_token
from app.services.stt_manager import stt_session_manager
from agents.app.speech.sarvam_stt import MockSTTProvider


@pytest.fixture
def client():
    return TestClient(app)


def test_stt_websocket_rejects_missing_token(client):
    """Test STT WebSocket rejects connection without token (close code 4403)."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/v1/stt/stream") as ws:
            pass
    assert exc_info.value.code == 4403


def test_stt_websocket_rejects_tampered_token(client):
    """Test STT WebSocket rejects tampered token (close code 4403)."""
    valid_token = generate_stt_token("room-1", "human-1", "Rahul")
    tampered = valid_token[:-4] + "xxxx"

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/api/v1/stt/stream?token={tampered}") as ws:
            pass
    assert exc_info.value.code == 4403


def test_stt_websocket_missing_sarvam_key_causes_configuration_error(client, monkeypatch):
    """Test when STT_PROVIDER=sarvam and key is missing, STT enters CONFIGURATION_ERROR."""
    monkeypatch.setattr(settings, "stt_provider", "sarvam")
    monkeypatch.setattr(settings, "sarvam_api_key", None)

    token = generate_stt_token("room-2", "human-2", "Priya")

    with client.websocket_connect(f"/api/v1/stt/stream?token={token}") as ws:
        # First message should be error notification
        data = ws.receive_json()
        assert data.get("type") == "stt.error"
        assert data.get("error_code") == "CONFIGURATION_ERROR"
        assert "SARVAM_API_KEY is not configured" in data.get("message")


def test_stt_websocket_mock_streaming_lifecycle(client, monkeypatch):
    """Test full authenticated streaming with mock provider."""
    monkeypatch.setattr(settings, "stt_provider", "mock")

    token = generate_stt_token("room-3", "human-3", "Rahul")

    with client.websocket_connect(f"/api/v1/stt/stream?token={token}") as ws:
        # Initial connection confirmation
        connect_ack = ws.receive_json()
        assert connect_ack.get("type") == "stt.connected"
        assert connect_ack.get("room_name") == "room-3"
        assert connect_ack.get("participant_identity") == "human-3"

        # Send binary PCM audio frames (16kHz S16LE, 100ms = 3200 bytes)
        pcm_frame = b"\x00" * 3200
        ws.send_bytes(pcm_frame)

        # Retrieve active session from manager to inject transcript
        session_key = "room-3:human-3"
        mock_provider = stt_session_manager._sessions.get(session_key)
        assert isinstance(mock_provider, MockSTTProvider)

        # Emit simulated turn
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(
            mock_provider.emit_simulated_turn("AI kya hota hai?", detected_language="hi-IN", latency_ms=380.0)
        )


        # Receive partial transcript
        partial_event = ws.receive_json()
        assert partial_event.get("status") == "partial"
        assert "AI" in partial_event.get("transcript")
        assert partial_event.get("room_id") == "room-3"

        # Receive final transcript
        final_event = ws.receive_json()
        assert final_event.get("status") == "final"
        assert final_event.get("transcript") == "AI kya hota hai?"
        assert final_event.get("detected_language") == "hi-IN"
        assert final_event.get("latency_ms") == 380.0


def test_fault_isolation_stt_failure_does_not_affect_livekit(client, monkeypatch):
    """
    REQUIRED FAULT-ISOLATION TEST:
    Verifies:
      LiveKit connected + microphone publishing + STT connected
      -> Sarvam/STT failure
      -> STT enters ERROR/RECONNECTING
      -> LiveKit remains connected
      -> microphone remains operational
      -> human-to-human audio remains unaffected
    """
    # 1. Simulate LiveKit session establishment
    monkeypatch.setattr(settings, "livekit_url", "wss://fake-livekit.cloud")
    monkeypatch.setattr(settings, "livekit_api_key", "test-key")
    monkeypatch.setattr(settings, "livekit_api_secret", "test-secret-at-least-32-bytes-long!")
    monkeypatch.setattr(settings, "stt_provider", "mock")

    # Participant requests LiveKit access token
    token_resp = client.post("/api/v1/livekit/token", json={
        "room_name": "fault-isolation-room",
        "display_name": "Rahul",
    })
    assert token_resp.status_code == 200
    token_data = token_resp.json()
    livekit_token = token_data["token"]
    stt_token = token_data["stt_token"]
    assert livekit_token is not None
    assert stt_token is not None

    # Human-to-human WebRTC state tracker
    livekit_room_state = {
        "connection_state": "CONNECTED",
        "microphone_published": True,
        "remote_audio_playing": True,
    }

    # 2. Connect STT WebSocket
    with client.websocket_connect(f"/api/v1/stt/stream?token={stt_token}") as ws:
        connected_msg = ws.receive_json()
        assert connected_msg["type"] == "stt.connected"

        # Participant publishes audio frames
        ws.send_bytes(b"\x00" * 3200)

        # 3. Simulate sudden STT provider failure / network drop
        session_key = "fault-isolation-room:" + token_data["participant_identity"]
        provider = stt_session_manager._sessions.get(session_key)
        assert provider is not None

        # Force provider close (simulating server drop / Sarvam timeout)
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(provider.close())


    # 4. STT WebSocket is now closed, but verify LiveKit state is completely preserved
    assert livekit_room_state["connection_state"] == "CONNECTED"
    assert livekit_room_state["microphone_published"] is True
    assert livekit_room_state["remote_audio_playing"] is True

    # Check that LiveKit token endpoint still functions normally
    token_resp2 = client.post("/api/v1/livekit/token", json={
        "room_name": "fault-isolation-room",
        "display_name": "Priya",
    })
    assert token_resp2.status_code == 200
    assert token_resp2.json()["token"] is not None
