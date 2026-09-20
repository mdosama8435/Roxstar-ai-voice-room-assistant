"""
Phase 3D: LiveKit Audio Publisher — Real WebRTC audio track publication.

Architecture (per Phase 3D spec):
  Sarvam TTS (PCM bytes, linear16, 24kHz, mono)
      ↓
  base64.b64decode() [done in SarvamTTSProvider]
      ↓
  AudioFrame(data, sample_rate=24000, num_channels=1, samples_per_channel=N)
      ↓
  rtc.AudioSource.capture_frame(frame)
      ↓
  rtc.LocalAudioTrack.create_audio_track("tts-<agent_id>", source)
      ↓
  room.local_participant.publish_track(track)
      ↓
  Human hears AI audio through LiveKit WebRTC

Audio Format Contract (verified):
  - Source codec: linear16 (from Sarvam)
  - Sample rate: 24000 Hz
  - Channels: 1 (mono)
  - Bit depth: 16-bit signed int
  - Frame duration: 20ms
  - Samples per frame: 24000 * 0.020 = 480
  - Bytes per frame: 480 * 2 = 960

Cancellation:
  - Each request has a request_id and sequence counter
  - Audio queue is cleared on cancellation/barge-in
  - Late chunks from old requests are discarded by sequence check

Turn isolation:
  - Only the selected AI agent's audio is published
  - Non-selected agent produces no audio
  - Simultaneous publication from both agents is prevented by turn lock
"""

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger("roxstar.tts.livekit_publisher")

# LiveKit RTC sample rate and frame parameters (verified against livekit==1.1.19 API)
_SAMPLE_RATE = 24000
_NUM_CHANNELS = 1
_SAMPLES_PER_FRAME = 480   # 20ms at 24kHz: 24000 * 0.020
_BYTES_PER_FRAME = _SAMPLES_PER_FRAME * 2  # int16 = 2 bytes per sample


def _extract_pcm_bytes(chunk) -> bytes:
    """Accept raw bytes or VerifiedPCMChunk from SarvamTTSProvider."""
    if chunk is None:
        return b""
    if isinstance(chunk, (bytes, bytearray, memoryview)):
        return bytes(chunk)
    pcm = getattr(chunk, "pcm", None)
    if isinstance(pcm, (bytes, bytearray)):
        # Enforce LiveKit AudioSource channel/rate match when metadata is present
        sample_rate = getattr(chunk, "sample_rate", _SAMPLE_RATE)
        channels = getattr(chunk, "channels", _NUM_CHANNELS)
        if sample_rate != _SAMPLE_RATE:
            raise ValueError(
                f"PCM sample_rate {sample_rate} does not match AudioSource {_SAMPLE_RATE}"
            )
        if channels != _NUM_CHANNELS:
            raise ValueError(
                f"PCM channels {channels} does not match AudioSource {_NUM_CHANNELS}"
            )
        return bytes(pcm)
    raise TypeError(f"Unsupported PCM chunk type: {type(chunk)!r}")


class LiveKitAudioPublisher:
    """
    Manages a LiveKit AudioSource + LocalAudioTrack for a single AI participant.

    One publisher instance per AI agent (ai_dost, ai_sathi).
    The non-selected agent's publisher receives no audio frames.

    Usage:
        publisher = LiveKitAudioPublisher(agent_id="dost", room=lk_room)
        await publisher.setup()
        await publisher.publish_pcm_stream(pcm_generator, request_id=..., turn_id=...)
        # On barge-in:
        await publisher.cancel_and_clear(request_id=...)
    """

    def __init__(
        self,
        agent_id: str,
        room=None,  # livekit.rtc.Room instance (optional; injected at runtime)
        queue_maxsize: int = 50,
    ):
        self.agent_id = agent_id
        self.room = room
        self.queue_maxsize = queue_maxsize

        self._audio_source = None    # livekit.rtc.AudioSource
        self._audio_track = None     # livekit.rtc.LocalAudioTrack
        self._published = False

        # Bounded async audio queue with backpressure
        self._audio_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=queue_maxsize)

        # Active request tracking for late-chunk discard
        self._active_request_id: Optional[str] = None
        self._active_sequence: int = 0
        self._cancel_events: dict[str, asyncio.Event] = {}

        self._publish_task: Optional[asyncio.Task] = None

    async def setup(self, room=None) -> None:
        """
        Initialize AudioSource and LocalAudioTrack.
        Must be called before publish_pcm_stream().

        Args:
            room: livekit.rtc.Room instance. If not provided, uses self.room.
        """
        if room:
            self.room = room

        try:
            from livekit import rtc
            # AudioSource: configured for verified Sarvam output format
            self._audio_source = rtc.AudioSource(
                sample_rate=_SAMPLE_RATE,
                num_channels=_NUM_CHANNELS,
                queue_size_ms=1000,  # 1 second internal buffer
            )
            # LocalAudioTrack: named per agent for identification
            track_name = f"tts-{self.agent_id}"
            self._audio_track = rtc.LocalAudioTrack.create_audio_track(
                track_name, self._audio_source
            )
            logger.info(
                f"LiveKitAudioPublisher setup complete: agent={self.agent_id}, "
                f"track={track_name}, sample_rate={_SAMPLE_RATE}Hz, "
                f"channels={_NUM_CHANNELS}, frame_duration=20ms"
            )
        except ImportError as exc:
            logger.error(
                f"livekit rtc SDK not available: {exc}. "
                "Install with: pip install livekit==1.1.19"
            )
            raise

    async def publish_track_to_room(self) -> None:
        """
        Publish the LocalAudioTrack to the LiveKit room.
        Must be called after setup() and after room is connected.
        """
        if not self.room or not self._audio_track:
            raise RuntimeError("Room and audio track must be set up before publishing")

        if self._published:
            return

        try:
            options = None
            try:
                from livekit.rtc import TrackPublishOptions, TrackSource
                options = TrackPublishOptions(source=TrackSource.SOURCE_MICROPHONE)
            except ImportError:
                pass

            if options:
                await self.room.local_participant.publish_track(self._audio_track, options)
            else:
                await self.room.local_participant.publish_track(self._audio_track)

            self._published = True
            logger.info(
                f"LiveKit audio track published: agent={self.agent_id}, "
                f"room={getattr(self.room, 'name', 'unknown')}"
            )
        except Exception as exc:
            logger.error(
                f"Failed to publish LiveKit audio track for agent={self.agent_id}: {exc}"
            )
            raise

    async def _frame_publisher_loop(self, request_id: str) -> None:
        """
        Background task: dequeues PCM chunks from bounded queue and
        feeds them to AudioSource.capture_frame().

        Validates:
        - AudioFrame byte length is a multiple of int16 size
        - samples_per_channel matches actual data length
        - Request is still active (discards late chunks from old requests)
        """
        from livekit import rtc

        while True:
            try:
                pcm_chunk = await self._audio_queue.get()

                if pcm_chunk is None:
                    # Sentinel: end of stream
                    self._audio_queue.task_done()
                    break

                # Discard late chunks from cancelled/old requests
                if self._active_request_id != request_id:
                    self._audio_queue.task_done()
                    logger.debug(
                        f"Discarding late audio chunk for old request_id={request_id} "
                        f"(active={self._active_request_id})"
                    )
                    continue

                try:
                    pcm_chunk = _extract_pcm_bytes(pcm_chunk)
                except (TypeError, ValueError) as exc:
                    logger.error(
                        f"Invalid PCM chunk for agent={self.agent_id}: {exc}"
                    )
                    self._audio_queue.task_done()
                    break

                # Validate PCM byte length before creating AudioFrame
                if len(pcm_chunk) == 0:
                    self._audio_queue.task_done()
                    continue

                # Ensure length is multiple of int16 (2 bytes)
                if len(pcm_chunk) % 2 != 0:
                    logger.warning(
                        f"Odd PCM byte length {len(pcm_chunk)} for request_id={request_id}; "
                        "truncating last byte"
                    )
                    pcm_chunk = pcm_chunk[:-1]

                samples_per_channel = len(pcm_chunk) // (_NUM_CHANNELS * 2)
                if samples_per_channel == 0:
                    self._audio_queue.task_done()
                    continue

                frame = rtc.AudioFrame(
                    data=pcm_chunk,
                    sample_rate=_SAMPLE_RATE,
                    num_channels=_NUM_CHANNELS,
                    samples_per_channel=samples_per_channel,
                )
                await self._audio_source.capture_frame(frame)
                self._audio_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    f"Error in audio publisher loop for agent={self.agent_id}: {exc}",
                    exc_info=True
                )
                self._audio_queue.task_done()
                break

    async def publish_pcm_stream(
        self,
        pcm_stream,  # AsyncIterator[bytes]
        request_id: str,
        turn_id: str,
    ) -> None:
        """
        Streams PCM bytes from Sarvam TTS → AudioFrame → LiveKit.

        This is the main integration point called by the TTS service.
        Sets up the frame publisher loop as a background task for concurrency.

        Args:
            pcm_stream: AsyncIterator[bytes] from SarvamTTSProvider.synthesize_stream()
            request_id: TTS request ID for late-chunk detection
            turn_id: Conversation turn ID for logging
        """
        if not self._audio_source:
            raise RuntimeError(
                "LiveKitAudioPublisher not set up. Call setup() first."
            )

        # Register this as the active request
        self._active_request_id = request_id
        self._active_sequence += 1
        cancel_event = asyncio.Event()
        self._cancel_events[request_id] = cancel_event

        # Start frame publisher loop
        self._publish_task = asyncio.create_task(
            self._frame_publisher_loop(request_id),
            name=f"audio-publish-{self.agent_id}-{request_id[:8]}"
        )

        chunks_published = 0
        bytes_published = 0

        try:
            async for pcm_chunk in pcm_stream:
                # Check cancellation before queuing each chunk
                if cancel_event.is_set():
                    logger.info(
                        f"TTS audio publication cancelled: agent={self.agent_id}, "
                        f"request_id={request_id}, chunks_published={chunks_published}"
                    )
                    break

                if pcm_chunk:
                    # Bounded queue: blocks (backpressure) if consumer is slow
                    await self._audio_queue.put(pcm_chunk)
                    chunks_published += 1
                    try:
                        raw = _extract_pcm_bytes(pcm_chunk)
                        bytes_published += len(raw)
                    except (TypeError, ValueError):
                        # Frame loop will surface invalid chunks; keep count best-effort
                        pass

            # Send sentinel to end publisher loop
            await self._audio_queue.put(None)
            # Wait for all queued frames to be published
            await self._publish_task

            logger.info(
                f"Audio publication complete: agent={self.agent_id}, "
                f"request_id={request_id}, chunks={chunks_published}, "
                f"bytes={bytes_published}"
            )

        except Exception as exc:
            logger.error(
                f"Error in publish_pcm_stream for agent={self.agent_id}: {exc}",
                exc_info=True
            )
            await self._cancel_and_cleanup(request_id)
            raise
        finally:
            self._cancel_events.pop(request_id, None)

    async def _cancel_and_cleanup(self, request_id: str) -> None:
        """Internal: cancel publish task and clear queue."""
        if self._publish_task and not self._publish_task.done():
            self._publish_task.cancel()
            try:
                await self._publish_task
            except (asyncio.CancelledError, Exception):
                pass
        self._clear_queue()

    def _clear_queue(self) -> None:
        """Clear all pending audio from bounded queue. Called on barge-in/cancellation."""
        cleared = 0
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.task_done()
                cleared += 1
            except asyncio.QueueEmpty:
                break
        if cleared > 0:
            logger.info(
                f"Audio queue cleared: agent={self.agent_id}, "
                f"discarded_chunks={cleared}"
            )

    async def cancel_current(self, request_id: Optional[str] = None) -> None:
        """
        Cancel active audio publication and clear pending queue.
        Called on barge-in or TTS cancellation.

        Args:
            request_id: If provided, only cancels matching request.
                       If None, cancels any active request.
        """
        target_id = request_id or self._active_request_id
        if target_id:
            event = self._cancel_events.get(target_id)
            if event:
                event.set()

        # Clear the queue immediately to stop pending frames
        self._clear_queue()

        # Put sentinel to stop publisher loop if it's waiting
        try:
            self._audio_queue.put_nowait(None)
        except asyncio.QueueFull:
            pass

        if self._publish_task and not self._publish_task.done():
            self._publish_task.cancel()
            try:
                await asyncio.wait_for(self._publish_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        logger.info(
            f"LiveKit audio publication cancelled: agent={self.agent_id}, "
            f"request_id={target_id}"
        )

    async def close(self) -> None:
        """Clean up publisher resources."""
        await self.cancel_current()
        if self._audio_track and self.room and self._published:
            try:
                await self.room.local_participant.unpublish_track(self._audio_track.sid)
            except Exception as exc:
                logger.debug(f"Error unpublishing track on close: {exc}")
        self._audio_source = None
        self._audio_track = None
        self._published = False
