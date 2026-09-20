"""
Phase 3D Step 2: Dual AI LiveKit room lifecycle (Dost + Sathi).

agents/ owns media: two identifiable AI participants, each with a silent
LiveKitAudioPublisher track. No TTS generation in this step.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from agents.app.agents.personas import DOST_PERSONA, SATHI_PERSONA
from agents.app.config import AgentSettings, agent_settings
from agents.app.livekit.ai_participant import AIParticipantSession

logger = logging.getLogger("roxstar.agents.livekit.room_lifecycle")

# Stable opaque identities used across orchestration / frontend text paths.
AI_DOST_IDENTITY = "ai_dost"
AI_SATHI_IDENTITY = "ai_sathi"


class AIRoomLifecycle:
    """
    Manages AI Dost and AI Sathi LiveKit sessions in one room.

    Each persona is a separate rtc.Room local participant with its own
    LiveKitAudioPublisher. Tracks are published but remain silent until TTS.
    """

    def __init__(
        self,
        settings: Optional[AgentSettings] = None,
        room_name: Optional[str] = None,
    ) -> None:
        self.settings = settings or agent_settings
        self.room_name = (room_name or self.settings.livekit_room_name).strip()
        self._sessions: list[AIParticipantSession] = []
        self._started = False
        self._lock = asyncio.Lock()

    @property
    def is_configured(self) -> bool:
        return bool(
            self.settings.livekit_url
            and self.settings.livekit_api_key
            and self.settings.livekit_api_secret
            and self.room_name
        )

    @property
    def sessions(self) -> list[AIParticipantSession]:
        return list(self._sessions)

    @property
    def is_started(self) -> bool:
        return self._started

    def get_session(self, agent_id: str) -> Optional[AIParticipantSession]:
        for session in self._sessions:
            if session.agent_id == agent_id:
                return session
        return None

    def all_connected(self) -> bool:
        return bool(self._sessions) and all(s.is_connected for s in self._sessions)

    async def ensure_room(self, room_name: str) -> None:
        """
        Guarantee both AI participants are connected in ``room_name``.

        Humans may join arbitrary rooms; TTS audio only reaches them if AI
        publishers are in the same LiveKit room. Rejoins when the target
        differs or sessions have dropped.
        """
        target = (room_name or "").strip()
        if not target:
            raise RuntimeError("ensure_room requires a non-empty room_name")

        async with self._lock:
            if self._started and self.room_name == target and self.all_connected():
                logger.info(
                    "AI room lifecycle already in target room",
                    extra={
                        "room_name": target,
                        "participants": [s.identity for s in self._sessions],
                    },
                )
                return

            logger.info(
                "AI room lifecycle ensuring human room",
                extra={
                    "from_room": self.room_name,
                    "to_room": target,
                    "was_started": self._started,
                    "was_connected": self.all_connected(),
                },
            )

            # Best-effort teardown with timeout — never block TTS forever on a
            # half-dead LiveKit session after the previous human left the room.
            old_sessions = list(self._sessions)
            self._sessions = []
            self._started = False
            self.room_name = target
            for session in reversed(old_sessions):
                try:
                    await asyncio.wait_for(session.disconnect(), timeout=3.0)
                except Exception as exc:
                    logger.warning(
                        "AI session disconnect during ensure_room: %s",
                        type(exc).__name__,
                        extra={"agent_id": getattr(session, "agent_id", None)},
                    )

            try:
                await asyncio.wait_for(self._start_unlocked(), timeout=20.0)
            except Exception as exc:
                logger.error(
                    "AI room lifecycle failed to join human room: %s",
                    type(exc).__name__,
                    extra={"room_name": target},
                )
                self._sessions = []
                self._started = False
                raise



    async def speak(
        self,
        agent_id: str,
        text: str,
        *,
        speaker: str,
        tts_provider,
        turn_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        """Publish TTS audio on the selected AI participant track only."""
        session = self.get_session(agent_id)
        if session is None:
            raise RuntimeError(f"No AI session for agent_id={agent_id}")
        return await session.speak_text(
            text,
            speaker=speaker,
            tts_provider=tts_provider,
            turn_id=turn_id,
            request_id=request_id,
        )

    def _build_sessions(self) -> list[AIParticipantSession]:
        url = self.settings.livekit_url
        key = self.settings.livekit_api_key
        secret = self.settings.livekit_api_secret
        if not (url and key and secret):
            raise RuntimeError(
                "LiveKit is not configured. Set LIVEKIT_URL, LIVEKIT_API_KEY, "
                "and LIVEKIT_API_SECRET before starting the AI room lifecycle."
            )

        queue_maxsize = self.settings.tts_audio_queue_maxsize
        specs = (
            {
                "agent_id": DOST_PERSONA.id,
                "identity": AI_DOST_IDENTITY,
                "display_name": DOST_PERSONA.name,
            },
            {
                "agent_id": SATHI_PERSONA.id,
                "identity": AI_SATHI_IDENTITY,
                "display_name": SATHI_PERSONA.name,
            },
        )
        return [
            AIParticipantSession(
                agent_id=spec["agent_id"],
                identity=spec["identity"],
                display_name=spec["display_name"],
                livekit_url=url,
                api_key=key,
                api_secret=secret,
                room_name=self.room_name,
                queue_maxsize=queue_maxsize,
            )
            for spec in specs
        ]

    async def start(self) -> None:
        """Connect both AI participants and publish silent audio tracks."""
        async with self._lock:
            await self._start_unlocked()

    async def _start_unlocked(self) -> None:
        if self._started:
            return
        if not self.is_configured:
            raise RuntimeError(
                "LiveKit is not configured. Set LIVEKIT_URL, LIVEKIT_API_KEY, "
                "LIVEKIT_API_SECRET, and LIVEKIT_ROOM_NAME."
            )

        self._sessions = self._build_sessions()
        connected: list[AIParticipantSession] = []
        try:
            for session in self._sessions:
                await session.connect()
                connected.append(session)
            self._started = True
            logger.info(
                "AI room lifecycle started (silent tracks)",
                extra={
                    "room_name": self.room_name,
                    "participants": [s.identity for s in self._sessions],
                },
            )
        except Exception:
            # Roll back any partially connected sessions
            for session in reversed(connected):
                try:
                    await session.disconnect()
                except Exception:
                    pass
            self._sessions = []
            self._started = False
            raise

    async def stop(self) -> None:
        """Disconnect both AI participants and clean up publishers."""
        async with self._lock:
            await self._stop_unlocked()

    async def _stop_unlocked(self) -> None:
        sessions = list(self._sessions)
        self._sessions = []
        self._started = False
        for session in reversed(sessions):
            try:
                await session.disconnect()
            except Exception as exc:
                logger.debug(
                    "Error stopping AI session %s: %s",
                    session.agent_id,
                    exc,
                )
        logger.info(
            "AI room lifecycle stopped",
            extra={"room_name": self.room_name},
        )
