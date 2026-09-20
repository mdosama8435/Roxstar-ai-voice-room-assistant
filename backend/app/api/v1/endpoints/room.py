from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List

router = APIRouter()


class RoomFeatureSummary(BaseModel):
    phase: str = "Phase 1: Foundation"
    livekit_integration: str = "Planned for Phase 2"
    supported_personas: List[str] = ["Roxstar AI Dost (Male, Hindi/Hinglish)", "Roxstar AI Sathi (Female, Hindi/Hinglish)"]
    supported_languages: List[str] = ["Hindi (hi)", "English (en)", "Roman Hinglish (hi-Latn)"]
    message: str = "LiveKit token generation and active room management will be implemented in Phase 2."


@router.get("/info", response_model=RoomFeatureSummary)
async def get_room_capabilities_info() -> RoomFeatureSummary:
    """
    Returns API contract information regarding room capabilities.
    Does NOT simulate or fake an active LiveKit room.
    """
    return RoomFeatureSummary()
