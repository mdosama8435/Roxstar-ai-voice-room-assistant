import asyncio
import base64
import json
import time
from typing import Any, AsyncIterator, Dict, Optional
import websockets
from websockets.exceptions import ConnectionClosed

from agents.app.config import agent_settings
from agents.app.observability import agent_logger
from agents.app.speech.interfaces import SpeechToTextProvider, STTTranscriptResult

logger = agent_logger


class SarvamSTTProvider:
    """
    Production-grade Sarvam AI Realtime STT Provider.
    Implements current saaras:v3-realtime WebSocket streaming protocol.
    Streams 16kHz linear PCM S16LE chunks, tracks utterance latency, and extracts
    multilingual transcriptions (Hindi, Hinglish, English).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        language_code: Optional[str] = None,
        sample_rate: Optional[int] = None,
        ws_url: str = "wss://api.sarvam.ai/speech-to-text-realtime/ws",
    ):
        self.api_key = api_key or agent_settings.sarvam_api_key
        self.model = model or agent_settings.sarvam_stt_model or "saaras:v3-realtime"
        self.language_code = language_code or agent_settings.sarvam_stt_language or "auto"
        self.sample_rate = sample_rate or agent_settings.sarvam_stt_sample_rate or 16000
        self.ws_url = ws_url

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._event_queue: asyncio.Queue[Optional[STTTranscriptResult]] = asyncio.Queue()
        self._is_running = False
        self._send_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None

        self._room_name: str = ""
        self._participant_identity: str = ""
        self._participant_name: str = ""
        self._utterance_start_time: Optional[float] = None

    async def connect(
        self,
        room_name: str,
        participant_identity: str,
        participant_name: str
    ) -> None:
        """
        Establishes real-time streaming WebSocket connection to Sarvam Saaras.
        Strictly requires valid SARVAM_API_KEY.
        """
        if not self.api_key or self.api_key.strip() in ("", "your_sarvam_api_key_placeholder"):
            raise RuntimeError(
                "SARVAM_API_KEY is not configured while STT_PROVIDER=sarvam. "
                "STT is disabled (CONFIGURATION_ERROR)."
            )

        self._room_name = room_name
        self._participant_identity = participant_identity
        self._participant_name = participant_name

        query_params = (
            f"?model={self.model}"
            f"&language_code={self.language_code}"
            f"&sample_rate={self.sample_rate}"
        )
        target_ws_url = f"{self.ws_url}{query_params}"

        headers = {
            "api-subscription-key": self.api_key.strip(),
        }

        logger.info(
            "Connecting to Sarvam Realtime STT WebSocket",
            extra={
                "room_id": room_name,
                "participant_id": participant_identity,
                "model": self.model,
                "language_code": self.language_code,
                "sample_rate": self.sample_rate,
            }
        )

        try:
            # websockets>=14 uses additional_headers; older used extra_headers
            try:
                self._ws = await websockets.connect(
                    target_ws_url,
                    additional_headers=headers,
                    ping_interval=20,
                    ping_timeout=10,
                )
            except TypeError:
                self._ws = await websockets.connect(
                    target_ws_url,
                    extra_headers=headers,
                    ping_interval=20,
                    ping_timeout=10,
                )
        except Exception as exc:
            logger.error(
                f"Failed to connect to Sarvam Realtime STT: {str(exc)}",
                extra={
                    "room_id": room_name,
                    "participant_id": participant_identity,
                }
            )
            raise

        self._is_running = True
        self._send_task = asyncio.create_task(self._send_loop())
        self._receive_task = asyncio.create_task(self._receive_loop())

        logger.info(
            "Sarvam Realtime STT session established successfully",
            extra={
                "room_id": room_name,
                "participant_id": participant_identity,
            }
        )

    async def push_audio_chunk(self, pcm_bytes: bytes) -> None:
        """
        Enqueues raw 16kHz S16LE PCM chunk for transmission to Sarvam.
        """
        if not self._is_running:
            return
        await self._audio_queue.put(pcm_bytes)

    async def flush(self) -> None:
        """
        Flushes pending audio buffer.
        """
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.task_done()
            except asyncio.QueueEmpty:
                break

    async def receive_events(self) -> AsyncIterator[STTTranscriptResult]:
        """
        Yields real-time STTTranscriptResult events as parsed from Sarvam WebSocket.
        """
        while self._is_running:
            try:
                event = await self._event_queue.get()
                if event is None:
                    break
                yield event
            except asyncio.CancelledError:
                break

    async def close(self) -> None:
        """
        Gracefully terminates STT streaming session.
        """
        self._is_running = False

        if self._send_task:
            self._send_task.cancel()
            self._send_task = None

        if self._receive_task:
            self._receive_task.cancel()
            self._receive_task = None

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        await self._event_queue.put(None)
        logger.info(
            "Sarvam Realtime STT session closed",
            extra={
                "room_id": self._room_name,
                "participant_id": self._participant_identity,
            }
        )

    async def _send_loop(self) -> None:
        """
        Background worker sending base64-encoded PCM audio chunks to Sarvam.
        """
        while self._is_running and self._ws:
            try:
                chunk = await self._audio_queue.get()
                if not chunk:
                    continue

                if self._utterance_start_time is None:
                    self._utterance_start_time = time.time()

                b64_audio = base64.b64encode(chunk).decode("ascii")
                msg = {
                    "event": "audio_input",
                    "audio": b64_audio,
                }
                await self._ws.send(json.dumps(msg))
                self._audio_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(
                    f"Error sending audio chunk to Sarvam: {str(exc)}",
                    extra={
                        "room_id": self._room_name,
                        "participant_id": self._participant_identity,
                    }
                )
                break

    async def _receive_loop(self) -> None:
        """
        Background worker reading and parsing events from Sarvam WebSocket.
        """
        while self._is_running and self._ws:
            try:
                raw_message = await self._ws.recv()
                if not raw_message:
                    continue

                data = json.loads(raw_message)
                event_type = data.get("event") or data.get("type", "")

                now = time.time()
                latency_ms: Optional[float] = None
                if self._utterance_start_time is not None:
                    latency_ms = round((now - self._utterance_start_time) * 1000, 2)

                if event_type == "session.begin":
                    logger.info(
                        "Sarvam STT session.begin received",
                        extra={
                            "room_id": self._room_name,
                            "participant_id": self._participant_identity,
                        }
                    )

                elif event_type == "vad.speech_start":
                    self._utterance_start_time = time.time()

                elif event_type in ("transcript.partial", "partial"):
                    text = data.get("text") or data.get("transcript") or ""
                    if text.strip():
                        result = STTTranscriptResult(
                            text=text.strip(),
                            is_final=False,
                            detected_language=data.get("detected_language") or data.get("language") or self.language_code,
                            language_confidence=data.get("language_confidence") or data.get("confidence"),
                            latency_ms=data.get("latency_ms") or latency_ms,
                            raw_event=data,
                        )
                        await self._event_queue.put(result)

                elif event_type in ("transcript.final", "final"):
                    text = data.get("text") or data.get("transcript") or ""
                    if text.strip():
                        result = STTTranscriptResult(
                            text=text.strip(),
                            is_final=True,
                            detected_language=data.get("detected_language") or data.get("language") or self.language_code,
                            language_confidence=data.get("language_confidence") or data.get("confidence"),
                            latency_ms=data.get("latency_ms") or latency_ms,
                            raw_event=data,
                        )
                        await self._event_queue.put(result)
                    self._utterance_start_time = None

                elif event_type == "vad.speech_end":
                    self._utterance_start_time = None

                elif event_type == "session.end":
                    logger.info("Sarvam STT session.end received")
                    break

                elif event_type == "error":
                    error_code = data.get("code", "UNKNOWN_ERROR")
                    error_msg = data.get("message", "Unknown Sarvam STT error")
                    is_fatal = data.get("is_fatal", False)
                    logger.error(
                        f"Sarvam STT structured error: code={error_code} fatal={is_fatal} msg={error_msg}",
                        extra={
                            "room_id": self._room_name,
                            "participant_id": self._participant_identity,
                        }
                    )
                    if is_fatal:
                        break

            except ConnectionClosed as exc:
                logger.warning(
                    f"Sarvam STT WebSocket connection closed: code={exc.code} reason={exc.reason}",
                    extra={
                        "room_id": self._room_name,
                        "participant_id": self._participant_identity,
                    }
                )
                break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    f"Error in Sarvam STT receive loop: {str(exc)}",
                    extra={
                        "room_id": self._room_name,
                        "participant_id": self._participant_identity,
                    }
                )
                break


class MockSTTProvider:
    """
    Explicit Mock STT Provider for automated unit and integration tests.
    Used ONLY when STT_PROVIDER=mock is explicitly configured.
    Visibly identified; never used as silent fallback.
    """

    def __init__(self, **kwargs):
        self._is_running = False
        self._event_queue: asyncio.Queue[Optional[STTTranscriptResult]] = asyncio.Queue()
        self._room_name = ""
        self._participant_identity = ""
        self._participant_name = ""

    async def connect(
        self,
        room_name: str,
        participant_identity: str,
        participant_name: str
    ) -> None:
        self._room_name = room_name
        self._participant_identity = participant_identity
        self._participant_name = participant_name
        self._is_running = True
        logger.info(
            "[MOCK STT ACTIVE - TESTING ONLY] Initialized mock STT provider session",
            extra={"room_id": room_name, "participant_id": participant_identity}
        )

    async def push_audio_chunk(self, pcm_bytes: bytes) -> None:
        """Mock ingests PCM frames without throwing."""
        if not self._is_running:
            return

    async def emit_simulated_turn(
        self,
        text: str,
        detected_language: str = "hi-IN",
        latency_ms: float = 450.0
    ) -> None:
        """Helper to inject simulated partial and final results in tests."""
        words = text.split()
        partial_text = " ".join(words[:max(1, len(words) // 2)])
        await self._event_queue.put(
            STTTranscriptResult(
                text=partial_text,
                is_final=False,
                detected_language=detected_language,
                language_confidence=0.85,
                latency_ms=round(latency_ms * 0.5, 1),
            )
        )
        await self._event_queue.put(
            STTTranscriptResult(
                text=text,
                is_final=True,
                detected_language=detected_language,
                language_confidence=0.96,
                latency_ms=latency_ms,
            )
        )

    async def receive_events(self) -> AsyncIterator[STTTranscriptResult]:
        while self._is_running:
            try:
                event = await self._event_queue.get()
                if event is None:
                    break
                yield event
            except asyncio.CancelledError:
                break

    async def flush(self) -> None:
        pass

    async def close(self) -> None:
        self._is_running = False
        await self._event_queue.put(None)


def create_stt_provider(
    provider_type: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    language_code: Optional[str] = None,
    sample_rate: Optional[int] = None,
) -> SpeechToTextProvider:
    """
    Factory creating configured STT provider instance.
    Defaults to SarvamSTTProvider unless STT_PROVIDER=mock is explicitly set.
    """
    selected_provider = (provider_type or agent_settings.stt_provider or "sarvam").lower().strip()

    if selected_provider == "mock":
        return MockSTTProvider()

    return SarvamSTTProvider(
        api_key=api_key,
        model=model,
        language_code=language_code,
        sample_rate=sample_rate,
    )
