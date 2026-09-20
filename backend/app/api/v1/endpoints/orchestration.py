import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.observability.logger import get_logger
from app.schemas.contracts import (
    ModalityType,
    OrchestrationDecision,
    TranscriptEvent,
)
from app.services.conversation_context import ContextSnapshot, conversation_context_manager
from app.services.orchestrator import orchestrator
from app.services.stt_auth import verify_stt_token_claims
from app.services.turn_lock import RoomLockInfo, turn_lock_manager

logger = get_logger("orchestration_endpoint")

router = APIRouter()


class TextChatRequest(BaseModel):
    """
    Request payload for authenticated text chat orchestration.
    """
    room_name: str = Field(..., description="Target LiveKit room name")
    text: str = Field(..., min_length=1, max_length=2000, description="Text message content")
    # Optional parameters; if supplied, they must strictly match the token claims
    participant_identity: Optional[str] = Field(None, description="Expected participant identity")
    display_name: Optional[str] = Field(None, description="Expected display name")
    token: Optional[str] = Field(None, description="Signed session token (if not sent in Authorization header)")


@router.post("/text-chat", response_model=OrchestrationDecision)
async def handle_text_chat_turn(
    request: TextChatRequest,
    authorization: Optional[str] = Header(None),
    token_query: Optional[str] = Query(None, alias="token"),
) -> OrchestrationDecision:
    """
    Cryptographically authenticated endpoint for text chat conversation turns.
    
    Security & Anti-Bypass Guarantees:
    - Rejects unauthenticated requests with HTTP 401.
    - Validates cryptographic signature and expiration of session token.
    - Strictly derives participant_identity and room_name from authenticated claims.
    - Validates that request room_name and participant_identity match claims.
    - Feeds into the EXACT same TurnDetector -> Context -> Eligibility -> Routing -> Lock pipeline.
    """
    # 1. Extract session token
    raw_token = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization[7:].strip()
    elif token_query:
        raw_token = token_query.strip()
    elif request.token:
        raw_token = request.token.strip()

    if not raw_token:
        logger.warning("orchestration_text_chat_rejected: missing authentication token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required session token in Authorization header or query"
        )

    # 2. Cryptographic Authentication & Claims Verification
    try:
        claims = verify_stt_token_claims(
            token=raw_token,
            expected_room_name=request.room_name,
            expected_participant_identity=request.participant_identity,
        )
    except ValueError as val_err:
        logger.warning(
            f"orchestration_text_chat_rejected: authentication failure: {str(val_err)}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Token verification failed: {str(val_err)}"
        )

    # 3. Create TranscriptEvent with modality=TEXT (source='text')
    event_id = f"txt-{uuid.uuid4().hex[:12]}"
    transcript_event = TranscriptEvent(
        event_id=event_id,
        room_id=claims.room_name,
        participant_identity=claims.participant_identity,
        participant_display_name=claims.display_name,
        transcript=request.text.strip(),
        status="final",
        provider="text_client",
        model="direct_text",
        detected_language="auto",
        sequence=0,
        modality=ModalityType.TEXT,
        timestamp=datetime.now(timezone.utc),
    )

    # 4. Orchestrate through identical Master Pipeline
    decision = await orchestrator.handle_transcript_event(transcript_event)

    if decision is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Orchestration failed to produce a decision for finalized turn"
        )

    return decision


@router.get("/rooms/{room_id}/context", response_model=ContextSnapshot)
async def get_room_context(
    room_id: str,
    authorization: Optional[str] = Header(None),
    token_query: Optional[str] = Query(None, alias="token"),
) -> ContextSnapshot:
    """
    Retrieves the current bounded in-memory context snapshot for a room.
    Requires a valid room-bound session token (same family as STT / text-chat).
    """
    _require_room_session_auth(room_id, authorization, token_query)
    return await conversation_context_manager.get_context_snapshot(room_id)


@router.get("/rooms/{room_id}/lock", response_model=Optional[RoomLockInfo])
async def get_room_lock(
    room_id: str,
    authorization: Optional[str] = Header(None),
    token_query: Optional[str] = Query(None, alias="token"),
) -> Optional[RoomLockInfo]:
    """
    Retrieves current response lock information for a room, or null if unlocked.
    Requires a valid room-bound session token.
    """
    _require_room_session_auth(room_id, authorization, token_query)
    return await turn_lock_manager.current_lock(room_id)


@router.post("/rooms/{room_id}/lock/release")
async def release_room_lock(
    room_id: str,
    authorization: Optional[str] = Header(None),
    token_query: Optional[str] = Query(None, alias="token"),
) -> Dict[str, Any]:
    """
    Manually releases room lock (for authenticated test teardown or recovery).
    Requires a valid room-bound session token.
    """
    _require_room_session_auth(room_id, authorization, token_query)
    released = await turn_lock_manager.release(room_id)
    return {"room_id": room_id, "released": released}


def _require_room_session_auth(
    room_id: str,
    authorization: Optional[str],
    token_query: Optional[str],
) -> None:
    """Reject unauthenticated access to room context / lock admin surfaces."""
    raw_token = None
    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization[7:].strip()
    elif token_query:
        raw_token = token_query.strip()

    if not raw_token:
        logger.warning(
            "orchestration_admin_rejected: missing authentication token",
            extra={"extra_data": {"room_id": room_id}},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required session token in Authorization header or query",
        )

    try:
        verify_stt_token_claims(
            token=raw_token,
            expected_room_name=room_id,
            expected_participant_identity=None,
        )
    except ValueError as val_err:
        logger.warning(
            f"orchestration_admin_rejected: authentication failure: {str(val_err)}",
            extra={"extra_data": {"room_id": room_id}},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Token verification failed: {str(val_err)}",
        )
