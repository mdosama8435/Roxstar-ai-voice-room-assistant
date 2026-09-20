from typing import Any, Callable, Dict, Protocol, runtime_checkable
from pydantic import BaseModel


class LiveKitRoomEvent(BaseModel):
    event_type: str
    room_id: str
    participant_id: str
    payload: Dict[str, Any] = {}


@runtime_checkable
class LiveKitTransportProtocol(Protocol):
    """
    Abstract interface for LiveKit WebRTC transport.
    Ensures WebRTC socket and audio track operations are decoupled from AI logic.
    """
    async def connect_room(self, url: str, token: str) -> None:
        ...

    async def disconnect(self) -> None:
        ...

    async def publish_audio_track(self, track_name: str) -> None:
        ...

    async def subscribe_audio_tracks(self, on_frame: Callable[[str, bytes], None]) -> None:
        ...

    async def broadcast_data_message(self, topic: str, data: bytes) -> None:
        ...
