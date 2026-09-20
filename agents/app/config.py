from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class AgentSettings(BaseSettings):
    """
    Agent worker configuration.
    Loads settings from environment variables with graceful defaults.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    worker_name: str = "roxstar-agent-worker"
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # LiveKit credentials (Phase 3D AI media participants)
    livekit_url: Optional[str] = Field(default=None, alias="LIVEKIT_URL")
    livekit_api_key: Optional[str] = Field(default=None, alias="LIVEKIT_API_KEY")
    livekit_api_secret: Optional[str] = Field(default=None, alias="LIVEKIT_API_SECRET")
    # Default matches frontend demo room (RoomControls / useLiveKitRoom)
    livekit_room_name: str = Field(default="roxstar-test", alias="LIVEKIT_ROOM_NAME")

    # Sarvam AI (Phase 3A STT)
    stt_provider: str = Field(default="sarvam", alias="STT_PROVIDER")
    sarvam_api_key: Optional[str] = Field(default=None, alias="SARVAM_API_KEY")
    sarvam_stt_model: str = Field(default="saaras:v3-realtime", alias="SARVAM_STT_MODEL")
    sarvam_stt_language: str = Field(default="auto", alias="SARVAM_STT_LANGUAGE")
    sarvam_stt_sample_rate: int = Field(default=16000, alias="SARVAM_STT_SAMPLE_RATE")

    # LLM Settings
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    llm_api_key: Optional[str] = Field(default=None, alias="LLM_API_KEY")
    llm_model: str = Field(default="gpt-4o-mini", alias="LLM_MODEL")

    # Memory Settings
    redis_url: Optional[str] = Field(default=None, alias="REDIS_URL")
    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")

    # Audio & Turn Detection Thresholds
    vad_silence_threshold_ms: int = 500
    barge_in_energy_threshold: float = 0.65
    turn_lock_timeout_seconds: int = 15

    # -------------------------------------------------------------------------
    # Phase 3D: Sarvam Bulbul v3 TTS Configuration
    # SARVAM_TTS_API_KEY is separate from SARVAM_API_KEY (STT). Never merge.
    # -------------------------------------------------------------------------
    tts_provider: str = Field(default="sarvam", alias="TTS_PROVIDER")
    sarvam_tts_api_key: Optional[str] = Field(default=None, alias="SARVAM_TTS_API_KEY")
    sarvam_tts_model: str = Field(default="bulbul:v3", alias="SARVAM_TTS_MODEL")
    sarvam_tts_language: str = Field(default="hi-IN", alias="SARVAM_TTS_LANGUAGE")
    # Live-verified bulbul:v3 female speaker (anushka rejected by provider)
    sarvam_tts_dost_speaker: str = Field(default="shubh", alias="SARVAM_TTS_DOST_SPEAKER")
    sarvam_tts_sathi_speaker: str = Field(default="priya", alias="SARVAM_TTS_SATHI_SPEAKER")
    sarvam_tts_pace: float = Field(default=1.0, alias="SARVAM_TTS_PACE")
    sarvam_tts_temperature: float = Field(default=0.6, alias="SARVAM_TTS_TEMPERATURE")
    # linear16 verified as supported codec in sarvamai SDK types
    sarvam_tts_output_codec: str = Field(default="linear16", alias="SARVAM_TTS_OUTPUT_CODEC")
    # 24000 Hz is bulbul:v3 default sample rate
    sarvam_tts_sample_rate: int = Field(default=24000, alias="SARVAM_TTS_SAMPLE_RATE")
    tts_chunk_min_chars: int = Field(default=40, alias="TTS_CHUNK_MIN_CHARS")
    tts_chunk_max_chars: int = Field(default=250, alias="TTS_CHUNK_MAX_CHARS")
    tts_audio_queue_maxsize: int = Field(default=50, alias="TTS_AUDIO_QUEUE_MAXSIZE")


agent_settings = AgentSettings()
