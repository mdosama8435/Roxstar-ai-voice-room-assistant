import uuid
from datetime import timedelta
from fastapi import APIRouter, HTTPException, status
from livekit import api

from app.config import settings
from app.observability.logger import app_logger
from app.schemas.contracts import LiveKitTokenRequest, LiveKitTokenResponse
from app.services.stt_auth import generate_stt_token

router = APIRouter()


@router.post("/token", response_model=LiveKitTokenResponse, status_code=status.HTTP_200_OK)
async def generate_livekit_token(request: LiveKitTokenRequest) -> LiveKitTokenResponse:
    """
    Generates a cryptographically signed LiveKit AccessToken for a human participant.
    
    Security & Privacy constraints:
    - Never uses PII (e.g. real user names) as the LiveKit participant identity.
    - Generates an opaque random UUID-backed identity: 'human-<opaque_id>'.
    - Grants minimal required permissions: join room, publish mic/data, subscribe.
    - Never exposes LIVEKIT_API_SECRET or logs generated JWT tokens.
    """
    # Check if LiveKit configuration is present
    if not (settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret):
        app_logger.warning(
            "Token generation requested but LiveKit credentials are not configured",
            extra={"extra_data": {"room_name": request.room_name}}
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LiveKit is not configured. Add LiveKit credentials (LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET) to the backend environment."
        )

    # Sanitize room name and display name
    clean_room_name = request.room_name.strip()
    clean_display_name = request.display_name.strip()

    if not clean_room_name or not clean_display_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="room_name and display_name must not be empty or whitespace only."
        )

    # Enforce opaque participant identity without PII
    if request.participant_identity and request.participant_identity.startswith("human-"):
        # Use provided opaque identity if already formatted
        participant_identity = request.participant_identity.strip()
    else:
        # Generate new opaque identity
        participant_identity = f"human-{uuid.uuid4().hex[:12]}"

    # Define minimal client video grants
    grants = api.VideoGrants(
        room_join=True,
        room=clean_room_name,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
    )

    try:
        token_builder = (
            api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
            .with_identity(participant_identity)
            .with_name(clean_display_name)
            .with_grants(grants)
            .with_ttl(timedelta(hours=6))
        )
        jwt_token = token_builder.to_jwt()
    except Exception as exc:
        app_logger.error(
            f"Failed to sign LiveKit access token: {str(exc)}",
            extra={"extra_data": {"room_name": clean_room_name, "participant_id": participant_identity}}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate LiveKit access token."
        )

    # Generate cryptographically signed STT session token bound to room, identity, and display name
    stt_token = generate_stt_token(
        room_name=clean_room_name,
        participant_identity=participant_identity,
        display_name=clean_display_name,
    )

    # Log token generation lifecycle (NO token or secret logged)
    app_logger.info(
        "LiveKit access token and STT session token generated successfully",
        extra={
            "room_id": clean_room_name,
            "participant_id": participant_identity,
            "event_type": "livekit_token_issued"
        }
    )

    return LiveKitTokenResponse(
        server_url=settings.livekit_url,
        token=jwt_token,
        room_name=clean_room_name,
        participant_identity=participant_identity,
        display_name=clean_display_name,
        stt_token=stt_token,
    )
