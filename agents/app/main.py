"""
Phase 3D Step 2: Agent worker entrypoint.

Owns AI Dost + AI Sathi LiveKit media lifecycle (silent published tracks).
Does not run TTS, LLM, STT, or orchestration in this step.
"""

import asyncio
import sys

from agents.app.agents.personas import DOST_PERSONA, SATHI_PERSONA
from agents.app.config import agent_settings
from agents.app.livekit.room_lifecycle import AIRoomLifecycle
from agents.app.observability import agent_logger


async def run_agent_worker(room_name: str | None = None) -> None:
    """
    Connect AI Dost and AI Sathi to the LiveKit room with silent audio tracks.

    Blocks until cancelled (KeyboardInterrupt / SIGINT). Always cleans up.
    If LiveKit credentials are missing, logs and exits without inventing media state.

    When AI_MEDIA_IN_BACKEND=true (default), the backend owns AI publishers for TTS
    and this worker skips joining to avoid duplicate ai_dost/ai_sathi participants.
    """
    import os

    if os.environ.get("AI_MEDIA_IN_BACKEND", "true").lower() in ("1", "true", "yes"):
        print(
            "AI_MEDIA_IN_BACKEND=true — backend owns AI LiveKit publishers. "
            "Agent worker skipping room join (no duplicate participants)."
        )
        agent_logger.info(
            "Agent worker skipped — AI media owned by backend",
            extra={"extra_data": {"ai_media_in_backend": True}},
        )
        return

    lifecycle = AIRoomLifecycle(settings=agent_settings, room_name=room_name)

    agent_logger.info(
        "Initializing RoxStar AI Agent Worker (Phase 3D media lifecycle)",
        extra={
            "extra_data": {
                "worker_name": agent_settings.worker_name,
                "personas_loaded": [DOST_PERSONA.name, SATHI_PERSONA.name],
                "livekit_configured": lifecycle.is_configured,
                "room_name": lifecycle.room_name,
            }
        },
    )
    print(f"RoxStar AI Agent Worker [{agent_settings.worker_name}] initialized.")
    print(f"Loaded Personas: '{DOST_PERSONA.name}' (Male) & '{SATHI_PERSONA.name}' (Female)")

    if not lifecycle.is_configured:
        print(
            "LiveKit is not configured. Set LIVEKIT_URL, LIVEKIT_API_KEY, "
            "LIVEKIT_API_SECRET (and optionally LIVEKIT_ROOM_NAME)."
        )
        agent_logger.warning(
            "AI room lifecycle not started — LiveKit credentials missing",
            extra={"extra_data": {"room_name": lifecycle.room_name}},
        )
        return

    try:
        await lifecycle.start()
        print(
            f"AI participants joined room '{lifecycle.room_name}' "
            f"with silent tracks (tts-dost, tts-sathi). Waiting…"
        )
        # Keep process alive; tracks remain silent until a later TTS step.
        await asyncio.Future()
    except asyncio.CancelledError:
        raise
    finally:
        await lifecycle.stop()
        print("AI room lifecycle stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(run_agent_worker())
    except KeyboardInterrupt:
        print("Agent worker stopped.")
        sys.exit(0)
