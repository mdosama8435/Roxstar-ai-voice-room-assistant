import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch

from agents.app.speech.interfaces import SpeechToTextProvider, STTTranscriptResult
from agents.app.speech.sarvam_stt import (
    SarvamSTTProvider,
    MockSTTProvider,
    create_stt_provider,
)


@pytest.mark.asyncio
async def test_mock_stt_provider_protocol_and_events():
    provider = MockSTTProvider()
    assert isinstance(provider, SpeechToTextProvider)

    await provider.connect("test-room", "human-1", "Rahul")
    await provider.push_audio_chunk(b"\x00" * 3200)

    # Trigger simulated turn
    asyncio.create_task(provider.emit_simulated_turn("AI kya hota hai bhai?", detected_language="hi-IN", latency_ms=420.0))

    events = []
    async for event in provider.receive_events():
        events.append(event)
        if event.is_final:
            break

    await provider.close()

    assert len(events) == 2
    # Partial
    assert events[0].is_final is False
    assert "AI" in events[0].text
    assert events[0].detected_language == "hi-IN"
    assert events[0].latency_ms is not None

    # Final
    assert events[1].is_final is True
    assert events[1].text == "AI kya hota hai bhai?"
    assert events[1].detected_language == "hi-IN"
    assert events[1].latency_ms == 420.0


@pytest.mark.asyncio
async def test_sarvam_stt_missing_api_key_raises_configuration_error():
    """Verify missing key strictly raises error without silent fallback."""
    provider = SarvamSTTProvider(api_key=None)
    with pytest.raises(RuntimeError, match="SARVAM_API_KEY is not configured"):
        await provider.connect("room-1", "human-1", "Rahul")


@pytest.mark.asyncio
async def test_sarvam_stt_websocket_events_parsing():
    """Verify parsing of saaras:v3-realtime events from simulated WebSocket."""
    provider = SarvamSTTProvider(api_key="test_sarvam_key_abc123")

    fake_ws = AsyncMock()
    # Messages from Sarvam server
    server_messages = [
        json.dumps({"event": "session.begin", "session_id": "sess-999"}),
        json.dumps({"event": "vad.speech_start", "timestamp": 12.5}),
        json.dumps({"event": "transcript.partial", "text": "AI kya", "language": "hi-IN"}),
        json.dumps({"event": "transcript.final", "text": "AI kya hota hai?", "detected_language": "hi-IN", "confidence": 0.98}),
        json.dumps({"event": "vad.speech_end"}),
        json.dumps({"event": "session.end"}),
    ]

    msg_idx = 0
    async def fake_recv():
        nonlocal msg_idx
        if msg_idx < len(server_messages):
            msg = server_messages[msg_idx]
            msg_idx += 1
            return msg
        # Block until cancelled
        await asyncio.sleep(10)
        return ""

    fake_ws.recv.side_effect = fake_recv
    fake_ws.send = AsyncMock()
    fake_ws.close = AsyncMock()

    with patch("websockets.connect", AsyncMock(return_value=fake_ws)):
        await provider.connect("room-demo", "human-10", "Priya")

        # Push audio chunk
        await provider.push_audio_chunk(b"\x01\x00" * 1600)
        await asyncio.sleep(0.05)

        # Check audio chunk was sent as base64 audio_input
        assert fake_ws.send.called
        sent_data = json.loads(fake_ws.send.call_args[0][0])
        assert sent_data["event"] == "audio_input"
        assert "audio" in sent_data

        # Receive events
        received_events = []
        async for event in provider.receive_events():
            received_events.append(event)
            if event.is_final:
                break

        await provider.close()

        assert len(received_events) >= 2
        # Partial
        assert received_events[0].is_final is False
        assert received_events[0].text == "AI kya"

        # Final
        assert received_events[1].is_final is True
        assert received_events[1].text == "AI kya hota hai?"
        assert received_events[1].detected_language == "hi-IN"
        assert received_events[1].language_confidence == 0.98


@pytest.mark.asyncio
async def test_participant_isolation():
    """Verify two participants have completely isolated provider sessions and queues."""
    p1 = MockSTTProvider()
    p2 = MockSTTProvider()

    await p1.connect("room-1", "human-rahul", "Rahul")
    await p2.connect("room-1", "human-priya", "Priya")

    asyncio.create_task(p1.emit_simulated_turn("Rahul speaking", detected_language="hi-IN"))
    asyncio.create_task(p2.emit_simulated_turn("Priya speaking", detected_language="en-IN"))

    p1_events = []
    async for e in p1.receive_events():
        p1_events.append(e)
        if e.is_final:
            break

    p2_events = []
    async for e in p2.receive_events():
        p2_events.append(e)
        if e.is_final:
            break

    await p1.close()
    await p2.close()

    assert p1_events[-1].text == "Rahul speaking"
    assert p2_events[-1].text == "Priya speaking"
    assert p1_events[-1].text != p2_events[-1].text
