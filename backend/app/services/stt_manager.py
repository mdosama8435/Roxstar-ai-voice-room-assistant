import asyncio
from typing import Dict, Optional

from app.config import settings
from app.observability.logger import get_logger
from agents.app.speech.interfaces import SpeechToTextProvider
from agents.app.speech.sarvam_stt import SarvamSTTProvider, MockSTTProvider

logger = get_logger("stt_manager")


class STTSessionManager:
    """
    Manages multi-user STT provider sessions with strict participant isolation.
    Each connected participant identity maintains an independent STT session.
    Zero audio mixing between participants.
    """

    def __init__(self):
        self._sessions: Dict[str, SpeechToTextProvider] = {}
        self._lock = asyncio.Lock()

    def _session_key(self, room_name: str, participant_identity: str) -> str:
        return f"{room_name}:{participant_identity}"

    async def get_or_create_session(
        self,
        room_name: str,
        participant_identity: str,
        display_name: str
    ) -> SpeechToTextProvider:
        """
        Retrieves existing session or creates a new isolated STT provider session
        for the given participant identity.
        """
        key = self._session_key(room_name, participant_identity)

        async with self._lock:
            if key in self._sessions:
                return self._sessions[key]

            provider_type = (settings.stt_provider or "sarvam").lower().strip()

            if provider_type == "mock":
                logger.info(
                    "[MOCK STT ACTIVE - TESTING ONLY] Creating Mock STT Provider",
                    extra={"room_id": room_name, "participant_id": participant_identity}
                )
                provider = MockSTTProvider()
            elif provider_type == "sarvam":
                if not settings.sarvam_api_key or settings.sarvam_api_key.strip() in ("", "your_sarvam_api_key_placeholder"):
                    logger.error(
                        "SARVAM_API_KEY is missing while STT_PROVIDER=sarvam. STT is DISABLED (CONFIGURATION_ERROR).",
                        extra={"room_id": room_name, "participant_id": participant_identity}
                    )
                    raise RuntimeError(
                        "SARVAM_API_KEY is not configured while STT_PROVIDER=sarvam. "
                        "STT is disabled (CONFIGURATION_ERROR)."
                    )

                provider = SarvamSTTProvider(
                    api_key=settings.sarvam_api_key,
                    model=settings.sarvam_stt_model,
                    language_code=settings.sarvam_stt_language,
                    sample_rate=settings.sarvam_stt_sample_rate,
                )
            else:
                raise ValueError(f"Unknown STT_PROVIDER '{provider_type}'. Must be 'sarvam' or 'mock'.")

            await provider.connect(
                room_name=room_name,
                participant_identity=participant_identity,
                participant_name=display_name
            )

            self._sessions[key] = provider
            logger.info(
                f"Created isolated STT session for participant ({provider_type})",
                extra={
                    "room_id": room_name,
                    "participant_id": participant_identity,
                    "provider": provider_type,
                    "active_sessions": len(self._sessions),
                }
            )
            return provider

    async def remove_session(
        self,
        room_name: str,
        participant_identity: str
    ) -> Optional[SpeechToTextProvider]:
        """
        Cleans up and removes an isolated participant STT session.
        """
        key = self._session_key(room_name, participant_identity)

        async with self._lock:
            provider = self._sessions.pop(key, None)
            if provider:
                try:
                    await provider.close()
                except Exception as exc:
                    logger.warning(
                        f"Error closing STT provider session: {exc}",
                        extra={"room_id": room_name, "participant_id": participant_identity}
                    )
                logger.info(
                    "Removed STT session",
                    extra={
                        "room_id": room_name,
                        "participant_id": participant_identity,
                        "remaining_sessions": len(self._sessions),
                    }
                )
            return provider

    def active_session_count(self) -> int:
        return len(self._sessions)


# Global singleton STT session manager
stt_session_manager = STTSessionManager()
