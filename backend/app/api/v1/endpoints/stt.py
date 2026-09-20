import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from livekit import api

from app.config import settings
from app.observability.logger import get_logger
from app.schemas.contracts import (
    LiveKitTranscriptDataMessage,
    TranscriptEvent,
)
from app.services.stt_auth import verify_stt_token_claims
from app.services.stt_manager import stt_session_manager
from app.services.orchestrator import orchestrator

logger = get_logger("stt_gateway")


router = APIRouter()

# RFC 6455 Application-specific close codes
WS_4403_FORBIDDEN = 4403


async def _broadcast_to_livekit_room(room_name: str, payload_bytes: bytes) -> None:
    """
    Broadcasts finalized transcript turn across the LiveKit room via DataChannel.
    Topic: 'transcript.stream'
    Safe fallback: does nothing if LiveKit is not configured.
    """
    if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
        return

    try:
        async with api.LiveKitAPI(
            settings.livekit_url,
            settings.livekit_api_key,
            settings.livekit_api_secret,
        ) as lk_api:
            kind_enum = getattr(api, "DataPacketKind", None)
            packet_kind = getattr(kind_enum, "RELIABLE", 0) if kind_enum else 0
            req = api.SendDataRequest(
                room=room_name,
                data=payload_bytes,
                kind=packet_kind,
                topic="transcript.stream",
            )
            await lk_api.room.send_data(req)
    except Exception as exc:
        logger.warning(
            f"Failed to broadcast final transcript to LiveKit DataChannel: {exc}",
            extra={"room_id": room_name}
        )


@router.websocket("/stream")
async def stt_stream_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """
    Cryptographically authenticated real-time STT streaming WebSocket gateway.
    
    Security & Privacy constraints:
    - Never logs token or raw authentication query parameters.
    - Token is signed, short-lived, and cryptographically bound to room_name,
      participant_identity, and display_name.
    - Rejects invalid or expired tokens with close code 4403.
    - Strictly isolates participant sessions (no audio mixing).
    - Partials are streamed exclusively to the local client socket.
    - Finals are sent to the local socket and broadcasted to the room via LiveKit DataChannel.
    - STT failures/disconnects are isolated and never impact LiveKit WebRTC audio.
    """
    # 1. Cryptographic Authentication & Claims Verification
    if not token:
        logger.warning("stt_websocket_rejected: missing session token")
        await websocket.close(code=WS_4403_FORBIDDEN, reason="Missing STT session token")
        return

    try:
        claims = verify_stt_token_claims(token)
    except ValueError as val_err:
        logger.warning(
            f"stt_websocket_rejected: token validation failed: {str(val_err)}"
        )
        await websocket.close(code=WS_4403_FORBIDDEN, reason="Invalid or expired STT session token")
        return

    # Accept WebSocket connection after successful token authentication
    await websocket.accept()

    logger.info(
        "STT WebSocket connected and authenticated",
        extra={
            "room_id": claims.room_name,
            "participant_id": claims.participant_identity,
            "display_name": claims.display_name,
        }
    )

    # 2. Establish Isolated Participant STT Session
    try:
        provider = await stt_session_manager.get_or_create_session(
            room_name=claims.room_name,
            participant_identity=claims.participant_identity,
            display_name=claims.display_name,
        )
    except RuntimeError as config_err:
        # Explicit configuration error (e.g. SARVAM_API_KEY missing while STT_PROVIDER=sarvam)
        logger.error(
            f"STT session creation failed: {config_err}",
            extra={
                "room_id": claims.room_name,
                "participant_id": claims.participant_identity,
            }
        )
        await websocket.send_json({
            "type": "stt.error",
            "error_code": "CONFIGURATION_ERROR",
            "message": str(config_err),
            "is_fatal": True,
        })
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="STT configuration error")
        return
    except Exception as exc:
        logger.error(
            f"Unexpected error establishing STT provider: {exc}",
            extra={
                "room_id": claims.room_name,
                "participant_id": claims.participant_identity,
            }
        )
        await websocket.send_json({
            "type": "stt.error",
            "error_code": "INTERNAL_ERROR",
            "message": "Failed to establish STT session",
            "is_fatal": True,
        })
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Internal STT error")
        return

    # Send initial connection confirmation to client
    await websocket.send_json({
        "type": "stt.connected",
        "room_name": claims.room_name,
        "participant_identity": claims.participant_identity,
        "provider": settings.stt_provider,
        "model": settings.sarvam_stt_model,
    })

    # 3. Bi-directional Streaming
    sequence = 0

    async def client_receive_loop():
        """Reads incoming 16kHz binary PCM audio frames from the client."""
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break

                # Binary linear PCM S16LE frame from AudioWorklet resampler
                if "bytes" in message and message["bytes"]:
                    await provider.push_audio_chunk(message["bytes"])
                elif "text" in message and message["text"]:
                    # Client control messages (e.g. flush / ping)
                    pass
        except WebSocketDisconnect:
            pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(
                f"Error in STT client receive loop: {e}",
                extra={"room_id": claims.room_name, "participant_id": claims.participant_identity}
            )

    async def provider_event_loop():
        """Reads transcripts from STT provider and dispatches partials/finals."""
        nonlocal sequence
        try:
            async for result in provider.receive_events():
                sequence += 1
                event = TranscriptEvent(
                    event_id=f"evt-{uuid.uuid4().hex[:12]}",
                    room_id=claims.room_name,
                    participant_identity=claims.participant_identity,
                    participant_display_name=claims.display_name,
                    transcript=result.text,
                    status="final" if result.is_final else "partial",
                    provider=settings.stt_provider,
                    model=settings.sarvam_stt_model,
                    detected_language=result.detected_language or "auto",
                    language_confidence=result.language_confidence,
                    latency_ms=result.latency_ms,
                    sequence=sequence,
                    timestamp=datetime.now(timezone.utc),
                )

                # Feed event into Phase 3B master orchestration pipeline
                asyncio.create_task(orchestrator.handle_transcript_event(event))

                event_json = event.model_dump_json()

                if not result.is_final:

                    # PARTIAL: Send to originating client socket ONLY
                    await websocket.send_text(event_json)
                else:
                    # FINAL: Send to originating client socket AND broadcast to LiveKit room
                    await websocket.send_text(event_json)

                    # Broadcast over LiveKit DataChannel (topic: transcript.stream)
                    broadcast_msg = LiveKitTranscriptDataMessage(
                        event_id=event.event_id,
                        room_name=claims.room_name,
                        participant_identity=claims.participant_identity,
                        participant_display_name=claims.display_name,
                        transcript=event.transcript,
                        status="final",
                        detected_language=event.detected_language or "auto",
                        language_confidence=event.language_confidence,
                        latency_ms=event.latency_ms,
                        sequence=sequence,
                        timestamp=event.timestamp.isoformat(),
                    )
                    payload_bytes = broadcast_msg.model_dump_json().encode("utf-8")
                    asyncio.create_task(_broadcast_to_livekit_room(claims.room_name, payload_bytes))

                    logger.info(
                        f"Final transcript produced ({event.detected_language}, latency: {event.latency_ms}ms)",
                        extra={
                            "room_id": claims.room_name,
                            "participant_id": claims.participant_identity,
                            "latency_ms": event.latency_ms,
                            "language": event.detected_language,
                        }
                    )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(
                f"Error in STT provider event loop: {e}",
                extra={"room_id": claims.room_name, "participant_id": claims.participant_identity}
            )

    client_task = asyncio.create_task(client_receive_loop())
    event_task = asyncio.create_task(provider_event_loop())

    try:
        # Wait for either client disconnect or provider termination
        done, pending = await asyncio.wait(
            [client_task, event_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
    finally:
        # 4. Clean Teardown and Resource Cleanup
        await stt_session_manager.remove_session(claims.room_name, claims.participant_identity)
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info(
            "STT WebSocket session terminated cleanly",
            extra={"room_id": claims.room_name, "participant_id": claims.participant_identity}
        )
