"""Admin orchestration endpoints must require room-bound session tokens."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.stt_auth import generate_stt_token


@pytest.fixture
def client():
    return TestClient(app)


def test_room_context_requires_auth(client):
    res = client.get("/api/v1/orchestration/rooms/demo-room/context")
    assert res.status_code == 401


def test_room_lock_requires_auth(client):
    res = client.get("/api/v1/orchestration/rooms/demo-room/lock")
    assert res.status_code == 401


def test_room_lock_release_requires_auth(client):
    res = client.post("/api/v1/orchestration/rooms/demo-room/lock/release")
    assert res.status_code == 401


def test_room_context_accepts_valid_room_token(client):
    token = generate_stt_token(
        room_name="demo-room",
        participant_identity="human-test",
        display_name="Tester",
    )
    res = client.get(
        "/api/v1/orchestration/rooms/demo-room/context",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200


def test_room_context_rejects_wrong_room_token(client):
    token = generate_stt_token(
        room_name="other-room",
        participant_identity="human-test",
        display_name="Tester",
    )
    res = client.get(
        "/api/v1/orchestration/rooms/demo-room/context",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def test_health_is_liveness(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_ready_endpoint_exists(client):
    res = client.get("/ready")
    assert res.status_code in (200, 503)
    body = res.json()
    assert "checks" in body
    assert "livekit" in body["checks"]
