from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    """Verify exact required health payload."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "roxstar-backend"
    }


def test_system_status_endpoint():
    """Verify system status reflects real runtime properties."""
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "operational"
    assert data["phase"] == "Phase 1: Foundation"
    assert "python_version" in data
    assert "platform" in data
    assert "providers" in data
    assert isinstance(data["providers"]["livekit_configured"], bool)
