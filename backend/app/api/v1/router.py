from fastapi import APIRouter
from app.api.v1.endpoints import system, room, livekit, stt, orchestration

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(system.router, prefix="/system", tags=["System"])
api_v1_router.include_router(room.router, prefix="/rooms", tags=["Rooms"])
api_v1_router.include_router(livekit.router, prefix="/livekit", tags=["LiveKit"])
api_v1_router.include_router(stt.router, prefix="/stt", tags=["STT"])
api_v1_router.include_router(orchestration.router, prefix="/orchestration", tags=["Orchestration"])


