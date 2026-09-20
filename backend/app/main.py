import sys
from pathlib import Path

# Ensure project root is on sys.path so agents and backend packages resolve in all environments
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from contextlib import asynccontextmanager
from typing import Any, Dict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.observability.logger import app_logger, setup_structured_logger
from app.api.v1.router import api_v1_router


_IS_PRODUCTION = settings.environment.lower() == "production"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Respect LOG_LEVEL from settings (structured logger defaults to INFO otherwise)
    setup_structured_logger("roxstar", level=settings.log_level)

    # Startup logging
    app_logger.info(
        f"Starting {settings.app_name} v{settings.app_version} in {settings.environment} mode"
    )
    if settings.ai_media_in_backend:
        app_logger.info(
            "AI_MEDIA_IN_BACKEND=true — run ONE backend process / ONE worker, no --reload; "
            "horizontal scaling is unsupported while AI media is in-process"
        )

    # Phase 3D/3E: wire TTSService + bind AI LiveKit publishers (media plane).
    # Without a real Sarvam key, use MockTTSProvider — never claim real verification.
    app.state.ai_room_lifecycle = None
    try:
        from app.services.orchestrator import orchestrator
        from app.services.tts.tts_service import TTSService
        from agents.app.speech.sarvam_tts import MockTTSProvider, create_tts_provider

        if (settings.tts_provider or "").lower() in ("mock", "test") or not settings.effective_tts_api_key:
            tts_provider = MockTTSProvider()
            app_logger.info("TTSService wired with MockTTSProvider (no real Sarvam key / mock mode)")
        else:
            tts_provider = create_tts_provider(
                provider_type=settings.tts_provider,
                api_key=settings.effective_tts_api_key,
            )
            app_logger.info("TTSService wired with configured SarvamTTSProvider")

        tts_service = TTSService(
            tts_provider=tts_provider,
            min_chunk_chars=settings.tts_chunk_min_chars,
            max_chunk_chars=settings.tts_chunk_max_chars,
        )
        orchestrator.set_tts_service(tts_service)

        # Bind real LiveKit AI publishers so orchestrator TTS reaches the room.
        # Skip under pytest to avoid LiveKit room churn during unit tests.
        import os as _os
        _under_pytest = bool(_os.environ.get("PYTEST_CURRENT_TEST"))
        if (
            settings.ai_media_in_backend
            and not _under_pytest
            and settings.livekit_url
            and settings.livekit_api_key
            and settings.livekit_api_secret
            and settings.effective_tts_api_key
        ):
            from agents.app.livekit.room_lifecycle import AIRoomLifecycle
            from agents.app.config import AgentSettings

            # Reload agent settings at lifespan time (cwd-aware) and align LiveKit
            # credentials with the backend control plane — never use a stale import-time
            # AgentSettings snapshot that may have missed backend/.env.
            media_settings = AgentSettings(
                livekit_url=settings.livekit_url,
                livekit_api_key=settings.livekit_api_key,
                livekit_api_secret=settings.livekit_api_secret,
                livekit_room_name=settings.livekit_room_name,
                sarvam_tts_api_key=settings.effective_tts_api_key,
                sarvam_tts_model=settings.sarvam_tts_model,
                sarvam_tts_language=settings.sarvam_tts_language,
                sarvam_tts_dost_speaker=settings.sarvam_tts_dost_speaker,
                sarvam_tts_sathi_speaker=settings.sarvam_tts_sathi_speaker,
                sarvam_tts_output_codec=settings.sarvam_tts_output_codec,
                sarvam_tts_sample_rate=settings.sarvam_tts_sample_rate,
                tts_audio_queue_maxsize=settings.tts_audio_queue_maxsize,
            )

            lifecycle = AIRoomLifecycle(
                settings=media_settings,
                room_name=settings.livekit_room_name,
            )
            # Do not require a cold-start join into an empty default room.
            # Publishers are connected lazily via ensure_room(turn.room_id) before TTS
            # so AI audio always lands in the human's active LiveKit room.
            orchestrator.set_ai_room_lifecycle(lifecycle)
            app.state.ai_room_lifecycle = lifecycle
            app_logger.info(
                f"AI LiveKit lifecycle registered for on-demand room join "
                f"(default_room={settings.livekit_room_name}, "
                f"AI_MEDIA_IN_BACKEND={settings.ai_media_in_backend})"
            )
        elif not settings.effective_tts_api_key:
            app_logger.warning(
                "AI LiveKit publishers not registered: SARVAM TTS API key missing "
                "(set SARVAM_TTS_API_KEY or SARVAM_API_KEY)"
            )
        else:
            app_logger.info(
                "AI LiveKit publishers not registered "
                f"(ai_media_in_backend={settings.ai_media_in_backend}, under_pytest={_under_pytest})"
            )
    except Exception as exc:
        app_logger.warning(f"TTSService / AI media wiring skipped: {type(exc).__name__}: {exc}")

    yield
    # Shutdown
    lifecycle = getattr(app.state, "ai_room_lifecycle", None)
    if lifecycle is not None:
        try:
            await lifecycle.stop()
        except Exception as exc:
            app_logger.warning(f"AI room lifecycle stop error: {type(exc).__name__}: {exc}")
    app_logger.info(f"Shutting down {settings.app_name}")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Backend API foundation for RoxStar AI Voice Room Assistant",
    lifespan=lifespan,
    docs_url=None if _IS_PRODUCTION else "/docs",
    redoc_url=None if _IS_PRODUCTION else "/redoc",
    openapi_url=None if _IS_PRODUCTION else "/openapi.json",
)

# CORS Middleware — origins from CORS_ORIGINS (localhost defaults are development-only)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Root"])
async def root() -> Dict[str, Any]:
    """Service discovery for the backend root URL (avoids bare {"detail":"Not Found"})."""
    payload: Dict[str, Any] = {
        "service": "roxstar-backend",
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "ok",
        "health": "/health",
        "ready": "/ready",
        "api": "/api/v1",
    }
    if not _IS_PRODUCTION:
        payload["docs"] = "/docs"
    return payload


@app.get("/health", response_model=Dict[str, str], tags=["Health"])
async def health_check() -> Dict[str, str]:
    """
    Lightweight liveness probe. Does not call external providers.
    Guaranteed response format: {"status": "ok", "service": "roxstar-backend"}
    """
    return {
        "status": "ok",
        "service": "roxstar-backend",
    }


@app.get("/ready", tags=["Health"])
async def readiness_check() -> JSONResponse:
    """
    Production-safe readiness / config presence check.
    Does NOT call LiveKit, Sarvam, or LLM APIs — only inspects local configuration flags.
    """
    checks = {
        "livekit": settings.is_provider_configured("livekit"),
        "sarvam_stt": settings.is_provider_configured("sarvam"),
        "tts": bool(settings.effective_tts_api_key)
        or (settings.tts_provider or "").lower() in ("mock", "test"),
        "llm": settings.is_provider_configured("llm"),
        "stt_token_secret": bool(settings.stt_token_secret)
        or settings.environment.lower() != "production",
        "cors_configured": bool(settings.cors_origins_list),
        "ai_media_in_backend": bool(settings.ai_media_in_backend),
    }
    ready = all(
        [
            checks["livekit"],
            checks["sarvam_stt"],
            checks["tts"],
            checks["llm"],
            checks["stt_token_secret"],
            checks["cors_configured"],
        ]
    )
    body = {
        "status": "ready" if ready else "not_ready",
        "service": "roxstar-backend",
        "environment": settings.environment,
        "checks": checks,
    }
    return JSONResponse(content=body, status_code=200 if ready else 503)


# Include API v1 routes
app.include_router(api_v1_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=(settings.environment == "development"),
    )
