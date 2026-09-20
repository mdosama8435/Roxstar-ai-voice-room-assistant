import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional, Tuple

from app.config import settings
from app.observability.logger import get_logger
from app.schemas.contracts import STTSessionClaims

logger = get_logger("stt_auth")


def _get_signing_secret() -> str:
    """
    Returns HMAC secret for signing STT session tokens.
    Priority:
    1. STT_TOKEN_SECRET (dedicated secret)
    2. LIVEKIT_API_SECRET (dev fallback)
    3. Dev default (non-production only)

    In production, a dedicated STT_TOKEN_SECRET is required.
    """
    if settings.stt_token_secret:
        return settings.stt_token_secret
    if settings.environment.lower() == "production":
        raise RuntimeError("STT_TOKEN_SECRET must be explicitly configured in production environment.")
    if settings.livekit_api_secret:
        return settings.livekit_api_secret
    # Graceful fallback for local development/testing without credentials
    return "roxstar-stt-dev-secret-key-do-not-use-in-production"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = 4 - (len(data) % 4)
    if padding < 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


def generate_stt_token(
    room_name: str,
    participant_identity: str,
    display_name: str = "Participant",
    expiry_minutes: Optional[int] = None
) -> str:
    """
    Generates a cryptographically signed, short-lived STT WebSocket session token.
    The token is bound to room_name, participant_identity, display_name, and expiration time.
    Never logs or leaks the token.
    """
    if expiry_minutes is None:
        expiry_minutes = settings.stt_token_expiry_minutes

    now = int(time.time())
    exp = now + (expiry_minutes * 60)

    payload = {
        "room_name": room_name,
        "participant_identity": participant_identity,
        "display_name": display_name or "Participant",
        "iat": now,
        "exp": exp,
    }

    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64url_encode(payload_json)

    secret = _get_signing_secret().encode("utf-8")
    signature = hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).digest()
    sig_b64 = _b64url_encode(signature)

    # Return format: <payload_b64>.<sig_b64>
    return f"{payload_b64}.{sig_b64}"


def verify_stt_token(
    token: str,
    expected_room_name: Optional[str] = None,
    expected_participant_identity: Optional[str] = None
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Verifies the cryptographic signature, expiration, and claims of an STT session token.
    Never logs the token itself.
    
    Returns:
        (is_valid, claims_dict_or_None, error_reason_or_None)
    """
    if not token or "." not in token:
        return False, None, "Malformed STT session token format"

    parts = token.split(".")
    if len(parts) != 2:
        return False, None, "Malformed STT session token structure"

    payload_b64, sig_b64 = parts[0], parts[1]

    # Verify HMAC-SHA256 signature
    try:
        secret = _get_signing_secret().encode("utf-8")
    except Exception as e:
        logger.error(f"Failed to retrieve signing secret: {e}")
        return False, None, "Internal server configuration error"

    expected_sig = hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).digest()
    expected_sig_b64 = _b64url_encode(expected_sig)

    if not hmac.compare_digest(sig_b64, expected_sig_b64):
        logger.warning("stt_token_verification_failed: invalid cryptographic signature")
        return False, None, "Invalid cryptographic signature"

    # Decode and parse payload JSON
    try:
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        logger.warning("stt_token_verification_failed: failed to parse payload JSON")
        return False, None, "Invalid payload encoding"

    # Check expiration
    exp = payload.get("exp")
    if not exp or not isinstance(exp, (int, float)):
        return False, None, "Missing or invalid expiration in token"

    now = int(time.time())
    if now > exp:
        logger.warning(
            "stt_token_expired",
            extra={"room_name": payload.get("room_name"), "identity": payload.get("participant_identity")}
        )
        return False, None, "STT session token has expired"

    # Validate room_name match if provided
    token_room = payload.get("room_name")
    if expected_room_name and token_room != expected_room_name:
        logger.warning(
            "stt_token_room_mismatch",
            extra={"token_room": token_room, "expected_room": expected_room_name}
        )
        return False, None, "Token room does not match requested room"

    # Validate participant_identity match if provided
    token_identity = payload.get("participant_identity")
    if expected_participant_identity and token_identity != expected_participant_identity:
        logger.warning(
            "stt_token_identity_mismatch",
            extra={"token_identity": token_identity, "expected_identity": expected_participant_identity}
        )
        return False, None, "Token participant identity does not match requested identity"

    return True, payload, None


def verify_stt_token_claims(
    token: str,
    expected_room_name: Optional[str] = None,
    expected_participant_identity: Optional[str] = None
) -> STTSessionClaims:
    """
    Verifies the STT session token and returns a strongly-typed STTSessionClaims instance.
    Raises ValueError on validation failure.
    Never logs the token itself.
    """
    is_valid, claims_dict, reason = verify_stt_token(
        token,
        expected_room_name=expected_room_name,
        expected_participant_identity=expected_participant_identity
    )
    if not is_valid or not claims_dict:
        raise ValueError(reason or "Invalid STT session token")

    return STTSessionClaims(
        room_name=claims_dict.get("room_name", ""),
        participant_identity=claims_dict.get("participant_identity", ""),
        display_name=claims_dict.get("display_name", "Participant"),
        iat=int(claims_dict.get("iat", 0)),
        exp=int(claims_dict.get("exp", 0)),
    )
