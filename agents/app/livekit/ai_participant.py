"""
Phase 3D Step 2: Single AI participant LiveKit room + silent audio track lifecycle.

Owns one rtc.Room connection and one LiveKitAudioPublisher.
Does NOT synthesize or push TTS audio — track stays silent until a later step.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from agents.app.livekit.audio_publisher import LiveKitAudioPublisher

logger = logging.getLogger("roxstar.agents.livekit.ai_participant")


def mint_ai_participant_token(
    *,
    api_key: str,
    api_secret: str,
    room_name: str,
    identity: str,
    display_name: str,
) -> str:
    """
    Mint a LiveKit AccessToken for an AI media participant.

    Identity is opaque/non-PII (e.g. ai_dost / ai_sathi).
    Grants: join + publish audio + subscribe. No secrets are logged.
    """
    from livekit import api

    grants = api.VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
    )
    return (
        api.AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_name(display_name)
        .with_kind("agent")
        .with_grants(grants)
        .with_ttl(timedelta(hours=6))
        .to_jwt()
    )


class AIParticipantSession:
    """
    Lifecycle for one AI participant in a LiveKit room.

    Flow: mint token → connect Room → LiveKitAudioPublisher.setup →
    publish_track_to_room → remain silent (no PCM / no TTS).
    """

    def __init__(
        self,
        *,
        agent_id: str,
        identity: str,
        display_name: str,
        livekit_url: str,
        api_key: str,
        api_secret: str,
        room_name: str,
        queue_maxsize: int = 50,
    ) -> None:
        self.agent_id = agent_id
        self.identity = identity
        self.display_name = display_name
        self.livekit_url = livekit_url
        self._api_key = api_key
        self._api_secret = api_secret
        self.room_name = room_name

        self.room = None  # livekit.rtc.Room
        self.publisher = LiveKitAudioPublisher(
            agent_id=agent_id,
            queue_maxsize=queue_maxsize,
        )
        self._connected = False
        self._closing = False
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_track_published(self) -> bool:
        return bool(self.publisher._published)

    async def speak_text(
        self,
        text: str,
        *,
        speaker: str,
        tts_provider,
        turn_id: str | None = None,
        request_id: str | None = None,
    ):
        """
        Phase 3D Step 3: synthesize validated text via SarvamTTSProvider and
        publish through this session's LiveKitAudioPublisher.

        Does not invoke LLM. TTS failures are returned, not escalated to LLM retry.
        """
        from agents.app.speech.tts_livekit_bridge import synthesize_and_publish

        if not self._connected or not self.is_track_published:
            raise RuntimeError(
                f"AI participant {self.identity} is not connected with a published track"
            )
        return await synthesize_and_publish(
            provider=tts_provider,
            publisher=self.publisher,
            text=text,
            speaker=speaker,
            agent_id=self.agent_id,
            turn_id=turn_id,
            request_id=request_id,
        )

    async def connect(self) -> None:
        """Connect to LiveKit, set up AudioSource/LocalAudioTrack, publish silently."""
        async with self._lock:
            if self._connected:
                return

            from livekit import rtc

            token = mint_ai_participant_token(
                api_key=self._api_key,
                api_secret=self._api_secret,
                room_name=self.room_name,
                identity=self.identity,
                display_name=self.display_name,
            )

            room = rtc.Room()
            self._register_room_handlers(room)

            logger.info(
                "AI participant connecting",
                extra={
                    "agent_id": self.agent_id,
                    "identity": self.identity,
                    "room_name": self.room_name,
                },
            )

            try:
                await room.connect(self.livekit_url, token)
                await self.publisher.setup(room)
                await self.publisher.publish_track_to_room()
            except Exception:
                await self._cleanup_unlocked(room)
                raise

            self.room = room
            self._connected = True
            logger.info(
                "AI participant connected with silent audio track",
                extra={
                    "agent_id": self.agent_id,
                    "identity": self.identity,
                    "room_name": self.room_name,
                    "track": f"tts-{self.agent_id}",
                    "sample_rate": 24000,
                },
            )

    def _register_room_handlers(self, room) -> None:
        room.on("disconnected", self._on_disconnected)
        room.on("reconnecting", self._on_reconnecting)
        room.on("reconnected", self._on_reconnected)

    def _on_disconnected(self, reason=None) -> None:
        logger.warning(
            "AI participant disconnected",
            extra={
                "agent_id": self.agent_id,
                "identity": self.identity,
                "reason": str(reason) if reason is not None else None,
            },
        )
        if self._closing:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._handle_disconnect_cleanup())
        except RuntimeError:
            self._connected = False

    def _on_reconnecting(self) -> None:
        logger.info(
            "AI participant reconnecting",
            extra={"agent_id": self.agent_id, "identity": self.identity},
        )

    def _on_reconnected(self) -> None:
        logger.info(
            "AI participant reconnected — republishing silent track",
            extra={"agent_id": self.agent_id, "identity": self.identity},
        )
        if self._closing:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._handle_reconnect_republish())
        except RuntimeError:
            pass

    async def _handle_disconnect_cleanup(self) -> None:
        async with self._lock:
            self._connected = False
            await self.publisher.close()
            # Room object may already be disconnected by the SDK.
            self.publisher.room = None

    async def _handle_reconnect_republish(self) -> None:
        async with self._lock:
            if self._closing or self.room is None:
                return
            try:
                # Reset publish flag so publish_track_to_room runs again.
                self.publisher._published = False
                if self.publisher._audio_track is None:
                    await self.publisher.setup(self.room)
                else:
                    self.publisher.room = self.room
                await self.publisher.publish_track_to_room()
                self._connected = True
            except Exception as exc:
                logger.error(
                    "Failed to republish AI audio track after reconnect: %s",
                    exc,
                    extra={"agent_id": self.agent_id, "identity": self.identity},
                )
                await self._cleanup_unlocked(self.room)
                self._connected = False

    async def disconnect(self) -> None:
        """Graceful disconnect: unpublish track, close publisher, leave room."""
        async with self._lock:
            self._closing = True
            await self._cleanup_unlocked(self.room)
            self._closing = False

    async def _cleanup_unlocked(self, room) -> None:
        self._connected = False
        try:
            await self.publisher.close()
        except Exception as exc:
            logger.debug(
                "Publisher cleanup error for agent=%s: %s",
                self.agent_id,
                exc,
            )

        if room is not None:
            try:
                await room.disconnect()
            except Exception as exc:
                logger.debug(
                    "Room disconnect error for agent=%s: %s",
                    self.agent_id,
                    exc,
                )

        if self.room is room:
            self.room = None
        self.publisher.room = None
