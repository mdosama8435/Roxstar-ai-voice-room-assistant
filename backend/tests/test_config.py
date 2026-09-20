from app.config import Settings


def test_config_defaults_without_secrets():
    """Verify application configuration instantiates cleanly without requiring secrets."""
    test_settings = Settings(
        ENVIRONMENT="test",
        LOG_LEVEL="DEBUG",
        LIVEKIT_URL=None,
        LIVEKIT_API_KEY=None,
        LIVEKIT_API_SECRET=None,
        SARVAM_API_KEY=None,
        LLM_API_KEY=None,
        GEMINI_API_KEY=None,
    )
    assert test_settings.environment == "test"
    assert test_settings.is_provider_configured("livekit") is False
    assert test_settings.is_provider_configured("sarvam") is False
    assert test_settings.is_provider_configured("llm") is False


def test_cors_origins_parsing():
    """Verify CORS origins string is parsed into a clean list."""
    test_settings = Settings(
        CORS_ORIGINS="http://localhost:3000, http://127.0.0.1:3000, "
    )
    origins = test_settings.cors_origins_list
    assert len(origins) == 2
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins


def test_cors_default_origins_include_port_3000_and_3001():
    """Verify default CORS configuration allows both port 3000 and 3001 for local dev."""
    settings = Settings(ENVIRONMENT="development")
    origins = settings.cors_origins_list
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins
    assert "http://localhost:3001" in origins
    assert "http://127.0.0.1:3001" in origins


def _prod_kwargs(**overrides):
    base = dict(
        ENVIRONMENT="production",
        STT_TOKEN_SECRET="my-super-secret-key-12345",
        CORS_ORIGINS="https://app.example.com",
        LIVEKIT_URL="wss://example.livekit.cloud",
        LIVEKIT_API_KEY="lk_key",
        LIVEKIT_API_SECRET="lk_secret",
        SARVAM_API_KEY="sarvam_stt_key",
        SARVAM_TTS_API_KEY="sarvam_tts_key",
        GEMINI_API_KEY="gemini_live_key_abc",
    )
    base.update(overrides)
    return base


def test_production_stt_token_secret_validation():
    """Verify that in production mode, missing STT_TOKEN_SECRET raises validation error."""
    import pytest

    with pytest.raises(ValueError, match="STT_TOKEN_SECRET"):
        Settings(**_prod_kwargs(STT_TOKEN_SECRET=None))

    prod_settings = Settings(**_prod_kwargs())
    assert prod_settings.stt_token_secret == "my-super-secret-key-12345"


def test_production_rejects_localhost_cors_default():
    import pytest

    kw = _prod_kwargs()
    del kw["CORS_ORIGINS"]
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(**kw)


def test_production_rejects_wildcard_cors():
    import pytest

    with pytest.raises(ValueError, match="Wildcard"):
        Settings(**_prod_kwargs(CORS_ORIGINS="*"))


def test_production_requires_livekit_and_providers():
    import pytest

    with pytest.raises(ValueError, match="LIVEKIT"):
        Settings(**_prod_kwargs(LIVEKIT_URL=None, LIVEKIT_API_KEY=None, LIVEKIT_API_SECRET=None))

    with pytest.raises(ValueError, match="SARVAM_API_KEY"):
        Settings(**_prod_kwargs(SARVAM_API_KEY=None, SARVAM_TTS_API_KEY="tts_only"))

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        Settings(**_prod_kwargs(GEMINI_API_KEY=None, LLM_API_KEY=None))
