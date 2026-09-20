import pytest
from app.config import settings


@pytest.fixture(autouse=True)
def configure_mock_provider_for_unit_tests(monkeypatch, request):
    """
    Ensures offline unit and orchestration tests use MockLLMProvider explicitly
    to prevent hitting remote API rate limits (Google Free Tier 5 RPM limit),
    while preserving real Gemini access for opt-in live tests.
    """
    allowlist = (
        "test_real_gemini_live_smoke_test",
        "test_llm_fallback",
        "test_fallback_smoke",
        "test_nvidia",
    )
    if not any(prefix in request.node.name or prefix in request.node.nodeid for prefix in allowlist):
        monkeypatch.setattr(settings, "llm_provider", "mock")
        monkeypatch.setattr(settings, "llm_primary_provider", "mock")
