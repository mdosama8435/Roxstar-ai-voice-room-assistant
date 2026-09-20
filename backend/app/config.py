from typing import Any, List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

# Localhost CORS defaults are development-only.
# Field default is empty; non-production applies localhost via cors_origins_list.
_DEV_CORS_DEFAULT = (
    "http://localhost:3000,http://127.0.0.1:3000,"
    "http://localhost:3001,http://127.0.0.1:3001"
)


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables and .env file.
    Development starts without provider credentials; production fails closed.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Server settings
    app_name: str = "RoxStar AI Voice Room Assistant Backend"
    app_version: str = "0.1.0"
    environment: str = Field(default="development", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    port: int = Field(default=8000, alias="PORT")
    host: str = Field(default="0.0.0.0", alias="HOST")
    cors_origins: str = Field(
        default="",
        alias="CORS_ORIGINS",
    )

    # LiveKit settings
    livekit_url: Optional[str] = Field(default=None, alias="LIVEKIT_URL")
    livekit_api_key: Optional[str] = Field(default=None, alias="LIVEKIT_API_KEY")
    livekit_api_secret: Optional[str] = Field(default=None, alias="LIVEKIT_API_SECRET")
    # LiveKit room name for AI media participants (must match frontend)
    livekit_room_name: str = Field(default="roxstar-test", alias="LIVEKIT_ROOM_NAME")
    # When true, backend owns AI LiveKit publishers and binds them to TTSService.
    # Agents worker should skip joining the same room to avoid duplicate AI participants.
    ai_media_in_backend: bool = Field(default=True, alias="AI_MEDIA_IN_BACKEND")

    # Speech AI Providers - Sarvam Realtime STT (Phase 3A)
    stt_provider: str = Field(default="sarvam", alias="STT_PROVIDER")
    sarvam_api_key: Optional[str] = Field(default=None, alias="SARVAM_API_KEY")
    sarvam_stt_model: str = Field(default="saaras:v3-realtime", alias="SARVAM_STT_MODEL")
    sarvam_stt_language: str = Field(default="auto", alias="SARVAM_STT_LANGUAGE")
    sarvam_stt_sample_rate: int = Field(default=16000, alias="SARVAM_STT_SAMPLE_RATE")

    # STT WebSocket Session Authentication
    stt_token_secret: Optional[str] = Field(default=None, alias="STT_TOKEN_SECRET")
    stt_token_expiry_minutes: int = Field(default=30, alias="STT_TOKEN_EXPIRY_MINUTES")

    # Phase 3B Orchestration & Turn Detection Settings
    turn_pause_threshold_ms: int = Field(default=1500, alias="TURN_PAUSE_THRESHOLD_MS")
    max_context_turns: int = Field(default=20, alias="MAX_CONTEXT_TURNS")
    bot_lock_ttl_seconds: int = Field(default=15, alias="BOT_LOCK_TTL_SECONDS")

    def model_post_init(self, __context: Any) -> None:
        if self.environment.lower() != "production":
            return
        self._validate_production_config()

    def _validate_production_config(self) -> None:
        """Fail closed when ENVIRONMENT=production and required config is missing/unsafe."""
        errors: List[str] = []

        if not self.stt_token_secret:
            errors.append("STT_TOKEN_SECRET must be explicitly set when ENVIRONMENT is 'production'")

        origins = self.cors_origins_list
        # Empty / unset CORS_ORIGINS is allowed in production (backend-before-frontend):
        # cors_origins_list resolves to [] — never localhost defaults, never "*".
        if origins:
            if any(o.strip() == "*" for o in origins):
                errors.append("Wildcard CORS_ORIGINS (*) is not allowed in production")
            elif any(
                "localhost" in o.lower() or "127.0.0.1" in o
                for o in origins
            ):
                errors.append(
                    "CORS_ORIGINS must not include localhost/127.0.0.1 origins in production"
                )

        if not (self.livekit_url and self.livekit_api_key and self.livekit_api_secret):
            errors.append("LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET are required in production")
        elif self.livekit_url and not (
            self.livekit_url.startswith("wss://") or self.livekit_url.startswith("ws://")
        ):
            errors.append("LIVEKIT_URL must be a ws:// or wss:// URL")

        if not self.sarvam_api_key or "placeholder" in (self.sarvam_api_key or "").lower():
            errors.append("SARVAM_API_KEY is required in production (STT)")

        if not self.effective_tts_api_key:
            errors.append(
                "SARVAM_TTS_API_KEY (or SARVAM_API_KEY fallback) is required in production (TTS)"
            )

        if not self.effective_gemini_api_key and self.effective_primary_provider == "gemini":
            errors.append("GEMINI_API_KEY (or LLM_API_KEY) is required in production")
        elif not self.is_provider_configured("llm"):
            errors.append("Primary LLM credentials are required in production")

        if errors:
            raise ValueError("; ".join(errors))

    # LLM Provider settings (Phase 3C Google Gemini Primary + Phase 3C.1 NVIDIA NIM Fallback)
    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    llm_primary_provider: Optional[str] = Field(default=None, alias="LLM_PRIMARY_PROVIDER")
    llm_fallback_provider: str = Field(default="nvidia", alias="LLM_FALLBACK_PROVIDER")
    llm_enable_fallback: bool = Field(default=True, alias="LLM_ENABLE_FALLBACK")

    # Primary Gemini configuration
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    llm_api_key: Optional[str] = Field(default=None, alias="LLM_API_KEY")
    llm_model: str = Field(default="gemini-3.5-flash-lite", alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.7, alias="LLM_TEMPERATURE")
    llm_max_output_tokens: int = Field(default=300, alias="LLM_MAX_OUTPUT_TOKENS")
    llm_timeout_seconds: float = Field(default=15.0, alias="LLM_TIMEOUT_SECONDS")

    # Secondary NVIDIA NIM configuration (Phase 3C.1)
    nvidia_api_key: Optional[str] = Field(default=None, alias="NVIDIA_API_KEY")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1", alias="NVIDIA_BASE_URL")
    nvidia_model: str = Field(default="meta/llama-3.2-11b-vision-instruct", alias="NVIDIA_MODEL")

    # Persistence & Caching (Optional for local testing)
    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")
    redis_url: Optional[str] = Field(default=None, alias="REDIS_URL")

    # -------------------------------------------------------------------------
    # Phase 3D: Sarvam Bulbul v3 TTS Configuration
    # NOTE: SARVAM_TTS_API_KEY is a SEPARATE credential from SARVAM_API_KEY (STT).
    # Never merge or confuse these two keys.
    # -------------------------------------------------------------------------
    tts_provider: str = Field(default="sarvam", alias="TTS_PROVIDER")
    # TTS API key: distinct from STT key. Backend-only. Never exposed to frontend.
    sarvam_tts_api_key: Optional[str] = Field(default=None, alias="SARVAM_TTS_API_KEY")
    sarvam_tts_model: str = Field(default="bulbul:v3", alias="SARVAM_TTS_MODEL")
    # hi-IN for Hindi/Hinglish. LLM generates the correct language; TTS synthesizes it.
    sarvam_tts_language: str = Field(default="hi-IN", alias="SARVAM_TTS_LANGUAGE")
    # Speakers: AI Dost (male)=shubh; AI Sathi (female)=priya
    # Note: bulbul:v3 rejects 'anushka' (v2-era). Verified live against Sarvam available list.
    sarvam_tts_dost_speaker: str = Field(default="shubh", alias="SARVAM_TTS_DOST_SPEAKER")
    sarvam_tts_sathi_speaker: str = Field(default="priya", alias="SARVAM_TTS_SATHI_SPEAKER")
    # Pace: 0.5-2.0 range (bulbul:v3 does NOT support pitch/loudness)
    sarvam_tts_pace: float = Field(default=1.0, alias="SARVAM_TTS_PACE")
    # Temperature: only bulbul:v3 supports this parameter
    sarvam_tts_temperature: float = Field(default=0.6, alias="SARVAM_TTS_TEMPERATURE")
    # Audio output: linear16 for raw PCM compatible with LiveKit AudioFrame
    # Verified: sarvamai SDK output_audio_codec accepts 'linear16' (from SDK type inspection)
    sarvam_tts_output_codec: str = Field(default="linear16", alias="SARVAM_TTS_OUTPUT_CODEC")
    # Sample rate: 24000 Hz is bulbul:v3 default; also supported: 8000, 16000, 22050
    sarvam_tts_sample_rate: int = Field(default=24000, alias="SARVAM_TTS_SAMPLE_RATE")

    # Text chunking policy (Phase 3D sentence buffering)
    # Min chars before sending to TTS (prevents micro-fragments)
    tts_chunk_min_chars: int = Field(default=40, alias="TTS_CHUNK_MIN_CHARS")
    # Max chars before forced flush at word boundary
    tts_chunk_max_chars: int = Field(default=250, alias="TTS_CHUNK_MAX_CHARS")
    # Max items in bounded audio queue (backpressure protection)
    tts_audio_queue_maxsize: int = Field(default=50, alias="TTS_AUDIO_QUEUE_MAXSIZE")

    @property
    def effective_tts_api_key(self) -> Optional[str]:
        """Returns SARVAM_TTS_API_KEY if configured. Falls back to SARVAM_API_KEY for shared keys.
        Never merges with GEMINI or NVIDIA keys.
        """
        raw = self.sarvam_tts_api_key or self.sarvam_api_key
        if raw and "placeholder" not in raw.lower() and raw.strip():
            return raw.strip()
        return None

    @property
    def is_tts_configured(self) -> bool:
        """Returns True if real TTS can be used (API key available)."""
        if self.tts_provider.lower() in ("mock", "test"):
            return True
        return bool(self.effective_tts_api_key)

    @property
    def effective_primary_provider(self) -> str:
        """Determines effective primary LLM provider (LLM_PRIMARY_PROVIDER takes precedence over LLM_PROVIDER)."""
        return (self.llm_primary_provider or self.llm_provider or "gemini").lower().strip()

    @property
    def effective_fallback_provider(self) -> str:
        """Determines effective fallback LLM provider."""
        return (self.llm_fallback_provider or "nvidia").lower().strip()

    @property
    def effective_gemini_api_key(self) -> Optional[str]:
        """Returns GEMINI_API_KEY or fallback LLM_API_KEY if non-empty and not a placeholder."""
        raw = self.gemini_api_key or self.llm_api_key
        if raw and "placeholder" not in raw.lower():
            return raw.strip()
        return None

    @property
    def effective_nvidia_api_key(self) -> Optional[str]:
        """Returns NVIDIA_API_KEY if non-empty and not a placeholder."""
        raw = self.nvidia_api_key
        if raw and "placeholder" not in raw.lower() and str(raw).strip():
            return str(raw).strip()
        return None

    @property
    def is_fallback_configured(self) -> bool:
        """Returns whether the fallback provider (NVIDIA) has valid credentials."""
        if self.effective_fallback_provider == "nvidia":
            return bool(self.effective_nvidia_api_key)
        if self.effective_fallback_provider in ("mock", "test"):
            return True
        return False

    @property
    def cors_origins_list(self) -> List[str]:
        raw = (self.cors_origins or "").strip()
        # Unset/empty: production → []; development/test → localhost defaults
        if not raw:
            if self.environment.lower() == "production":
                return []
            raw = _DEV_CORS_DEFAULT
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    def is_provider_configured(self, provider_name: str) -> bool:
        """Helper to inspect provider presence without exposing secrets."""
        p_name = provider_name.lower().strip()
        if p_name == "livekit":
            return bool(self.livekit_url and self.livekit_api_key and self.livekit_api_secret)
        if p_name == "sarvam":
            return bool(self.sarvam_api_key)
        if p_name == "gemini":
            return bool(self.effective_gemini_api_key)
        if p_name == "nvidia":
            return bool(self.effective_nvidia_api_key)
        if p_name == "llm":
            prim = self.effective_primary_provider
            if prim == "gemini":
                return bool(self.effective_gemini_api_key)
            if prim == "nvidia":
                return bool(self.effective_nvidia_api_key)
            if prim in ("mock", "test"):
                return True
            return bool(self.llm_api_key and "placeholder" not in self.llm_api_key.lower())
        if p_name == "redis":
            return bool(self.redis_url)
        if p_name == "database":
            return bool(self.database_url)
        return False


# Global singleton settings instance
settings = Settings()
