"""
Phase 3D Step 2: Focused tests for AI LiveKit room/audio lifecycle wiring.

These tests mock LiveKit RTC / AccessToken. They do NOT claim live room verification,
do NOT generate TTS audio, and do NOT invent speaking/latency/transcript state.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.app.agents.personas import DOST_PERSONA, SATHI_PERSONA
from agents.app.config import AgentSettings
from agents.app.livekit.ai_participant import AIParticipantSession, mint_ai_participant_token
from agents.app.livekit.audio_publisher import LiveKitAudioPublisher
from agents.app.livekit.room_lifecycle import (
    AI_DOST_IDENTITY,
    AI_SATHI_IDENTITY,
    AIRoomLifecycle,
)


def _settings(**overrides) -> AgentSettings:
    base = {
        "livekit_url": "wss://example.livekit.cloud",
        "livekit_api_key": "devkey",
        "livekit_api_secret": "secret",
        "livekit_room_name": "roxstar-test",
    }
    base.update(overrides)
    return AgentSettings(**base)


class TestMintAIParticipantToken:
    def test_mints_token_with_agent_identity_and_grants(self):
        mock_token = MagicMock()
        mock_token.with_identity.return_value = mock_token
        mock_token.with_name.return_value = mock_token
        mock_token.with_kind.return_value = mock_token
        mock_token.with_grants.return_value = mock_token
        mock_token.with_ttl.return_value = mock_token
        mock_token.to_jwt.return_value = "jwt-ai-dost"

        with patch("livekit.api.AccessToken", return_value=mock_token) as access_cls, patch(
            "livekit.api.VideoGrants"
        ) as grants_cls:
            jwt = mint_ai_participant_token(
                api_key="k",
                api_secret="s",
                room_name="roxstar-test",
                identity=AI_DOST_IDENTITY,
                display_name=DOST_PERSONA.name,
            )

        assert jwt == "jwt-ai-dost"
        access_cls.assert_called_once_with("k", "s")
        mock_token.with_identity.assert_called_once_with(AI_DOST_IDENTITY)
        mock_token.with_name.assert_called_once_with(DOST_PERSONA.name)
        mock_token.with_kind.assert_called_once_with("agent")
        grants_cls.assert_called_once()
        grant_kwargs = grants_cls.call_args.kwargs
        assert grant_kwargs["room_join"] is True
        assert grant_kwargs["room"] == "roxstar-test"
        assert grant_kwargs["can_publish"] is True


class TestAIParticipantSession:
    @pytest.mark.asyncio
    async def test_connect_sets_up_publisher_and_publishes_silent_track(self):
        session = AIParticipantSession(
            agent_id="dost",
            identity=AI_DOST_IDENTITY,
            display_name=DOST_PERSONA.name,
            livekit_url="wss://example.livekit.cloud",
            api_key="k",
            api_secret="s",
            room_name="roxstar-test",
        )

        mock_room = MagicMock()
        mock_room.connect = AsyncMock()
        mock_room.disconnect = AsyncMock()
        mock_room.on = MagicMock()

        with patch(
            "agents.app.livekit.ai_participant.mint_ai_participant_token",
            return_value="jwt",
        ), patch("livekit.rtc.Room", return_value=mock_room), patch.object(
            session.publisher, "setup", new_callable=AsyncMock
        ) as setup, patch.object(
            session.publisher, "publish_track_to_room", new_callable=AsyncMock
        ) as publish, patch.object(
            session.publisher, "publish_pcm_stream", new_callable=AsyncMock
        ) as pcm:
            await session.connect()

        assert session.is_connected is True
        assert session.room is mock_room
        setup.assert_awaited_once_with(mock_room)
        publish.assert_awaited_once()
        pcm.assert_not_called()  # silent by default — no TTS in this step
        mock_room.on.assert_any_call("disconnected", session._on_disconnected)
        mock_room.on.assert_any_call("reconnected", session._on_reconnected)

    @pytest.mark.asyncio
    async def test_disconnect_closes_publisher_and_room(self):
        session = AIParticipantSession(
            agent_id="sathi",
            identity=AI_SATHI_IDENTITY,
            display_name=SATHI_PERSONA.name,
            livekit_url="wss://example.livekit.cloud",
            api_key="k",
            api_secret="s",
            room_name="roxstar-test",
        )
        mock_room = MagicMock()
        mock_room.disconnect = AsyncMock()
        session.room = mock_room
        session._connected = True

        with patch.object(session.publisher, "close", new_callable=AsyncMock) as close:
            await session.disconnect()

        close.assert_awaited_once()
        mock_room.disconnect.assert_awaited_once()
        assert session.is_connected is False
        assert session.room is None

    @pytest.mark.asyncio
    async def test_connect_failure_cleans_up_partial_state(self):
        session = AIParticipantSession(
            agent_id="dost",
            identity=AI_DOST_IDENTITY,
            display_name=DOST_PERSONA.name,
            livekit_url="wss://example.livekit.cloud",
            api_key="k",
            api_secret="s",
            room_name="roxstar-test",
        )
        mock_room = MagicMock()
        mock_room.connect = AsyncMock()
        mock_room.disconnect = AsyncMock()
        mock_room.on = MagicMock()

        with patch(
            "agents.app.livekit.ai_participant.mint_ai_participant_token",
            return_value="jwt",
        ), patch("livekit.rtc.Room", return_value=mock_room), patch.object(
            session.publisher, "setup", new_callable=AsyncMock
        ), patch.object(
            session.publisher,
            "publish_track_to_room",
            new_callable=AsyncMock,
            side_effect=RuntimeError("publish failed"),
        ), patch.object(
            session.publisher, "close", new_callable=AsyncMock
        ) as close:
            with pytest.raises(RuntimeError, match="publish failed"):
                await session.connect()

        close.assert_awaited()
        mock_room.disconnect.assert_awaited()
        assert session.is_connected is False


class TestAIRoomLifecycle:
    def test_is_configured_false_without_credentials(self):
        lifecycle = AIRoomLifecycle(settings=_settings(livekit_url=None))
        assert lifecycle.is_configured is False

    def test_is_configured_true_with_credentials(self):
        lifecycle = AIRoomLifecycle(settings=_settings())
        assert lifecycle.is_configured is True

    @pytest.mark.asyncio
    async def test_start_creates_two_separate_publisher_sessions(self):
        settings = _settings()
        lifecycle = AIRoomLifecycle(settings=settings)

        created_sessions = []

        async def fake_connect(self):
            self._connected = True
            created_sessions.append(self)

        async def fake_disconnect(self):
            self._connected = False

        with patch.object(AIParticipantSession, "connect", fake_connect), patch.object(
            AIParticipantSession, "disconnect", fake_disconnect
        ):
            await lifecycle.start()

        assert lifecycle.is_started is True
        assert len(lifecycle.sessions) == 2

        dost = lifecycle.get_session("dost")
        sathi = lifecycle.get_session("sathi")
        assert dost is not None and sathi is not None
        assert dost is not sathi
        assert dost.identity == AI_DOST_IDENTITY
        assert sathi.identity == AI_SATHI_IDENTITY
        assert dost.display_name == DOST_PERSONA.name
        assert sathi.display_name == SATHI_PERSONA.name
        assert isinstance(dost.publisher, LiveKitAudioPublisher)
        assert isinstance(sathi.publisher, LiveKitAudioPublisher)
        assert dost.publisher is not sathi.publisher
        assert dost.publisher.agent_id == "dost"
        assert sathi.publisher.agent_id == "sathi"

        await lifecycle.stop()
        assert lifecycle.is_started is False
        assert lifecycle.sessions == []

    @pytest.mark.asyncio
    async def test_start_rolls_back_if_second_participant_fails(self):
        lifecycle = AIRoomLifecycle(settings=_settings())
        call_count = {"n": 0}

        async def flaky_connect(self):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("sathi connect failed")
            self._connected = True

        disconnect = AsyncMock()

        with patch.object(AIParticipantSession, "connect", flaky_connect), patch.object(
            AIParticipantSession, "disconnect", disconnect
        ):
            with pytest.raises(RuntimeError, match="sathi connect failed"):
                await lifecycle.start()

        assert lifecycle.is_started is False
        assert lifecycle.sessions == []
        assert disconnect.await_count >= 1

    @pytest.mark.asyncio
    async def test_start_raises_when_not_configured(self):
        lifecycle = AIRoomLifecycle(settings=_settings(livekit_api_secret=None))
        with pytest.raises(RuntimeError, match="LiveKit is not configured"):
            await lifecycle.start()

    @pytest.mark.asyncio
    async def test_ensure_room_rejoins_when_target_differs(self):
        """Regression 3F.10.1: AI publishers must move into the human's LiveKit room."""
        lifecycle = AIRoomLifecycle(settings=_settings(livekit_room_name="roxstar-test"))
        disconnect = AsyncMock()

        async def _connect(self):
            self._connected = True

        with patch.object(AIParticipantSession, "connect", _connect), patch.object(
            AIParticipantSession, "disconnect", disconnect
        ):
            await lifecycle.start()
            assert lifecycle.room_name == "roxstar-test"
            assert lifecycle.all_connected() is True

            await lifecycle.ensure_room("human-custom-room")
            assert lifecycle.room_name == "human-custom-room"
            assert lifecycle.is_started is True
            assert lifecycle.all_connected() is True
            # Moved rooms → previous sessions disconnected
            assert disconnect.await_count >= 2

            # Idempotent when already in target and connected
            prev_disconnect = disconnect.await_count
            await lifecycle.ensure_room("human-custom-room")
            assert disconnect.await_count == prev_disconnect


class TestMainEntrypoint:
    @pytest.mark.asyncio
    async def test_run_agent_worker_skips_when_unconfigured(self):
        from agents.app.main import run_agent_worker

        with patch(
            "agents.app.main.agent_settings",
            _settings(livekit_url=None, livekit_api_key=None, livekit_api_secret=None),
        ):
            await run_agent_worker()  # must return without hanging
