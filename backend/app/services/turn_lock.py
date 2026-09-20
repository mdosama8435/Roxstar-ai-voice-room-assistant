import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
from pydantic import BaseModel, Field

from app.config import settings
from app.observability.logger import get_logger
from app.schemas.contracts import BotType

logger = get_logger("turn_lock")


class RoomLockInfo(BaseModel):
    """Metadata representing an active AI response audio lock."""
    room_id: str
    selected_bot: BotType
    turn_id: str
    acquired_at: datetime
    expires_at: datetime

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


class TurnLockManager:
    """
    Room-Scoped Mutex Turn Lock Service.
    
    Guarantees:
    - Room isolation: Room A locking never affects Room B.
    - Single-speaker mutex: Only ONE bot may acquire the room audio turn at any time.
    - Async concurrency safety.
    - Automatic TTL expiration to prevent deadlocks if a response worker crashes.
    """

    def __init__(self, default_ttl_seconds: Optional[int] = None):
        self.default_ttl = default_ttl_seconds or settings.bot_lock_ttl_seconds or 15
        # room_id -> RoomLockInfo
        self._locks: Dict[str, RoomLockInfo] = {}
        # room_id -> asyncio.Lock
        self._room_mutexes: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def _get_room_mutex(self, room_id: str) -> asyncio.Lock:
        async with self._global_lock:
            if room_id not in self._room_mutexes:
                self._room_mutexes[room_id] = asyncio.Lock()
            return self._room_mutexes[room_id]

    async def acquire(
        self,
        room_id: str,
        bot: BotType,
        turn_id: str,
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """
        Attempts to acquire the single-speaker response lock for a room.
        
        Returns:
            True if acquired successfully; False if blocked by an active lock.
        """
        if bot == BotType.NONE:
            return False

        room_mutex = await self._get_room_mutex(room_id)
        async with room_mutex:
            now = datetime.now(timezone.utc)
            existing = self._locks.get(room_id)

            # Check if active lock exists and has not expired
            if existing is not None and not existing.is_expired:
                logger.warning(
                    f"Turn lock acquisition BLOCKED: Room '{room_id}' is currently locked by {existing.selected_bot.value} (turn {existing.turn_id})",
                    extra={
                        "room_id": room_id,
                        "requesting_bot": bot.value,
                        "requesting_turn": turn_id,
                        "holding_bot": existing.selected_bot.value,
                    }
                )
                return False

            # Acquire lock
            ttl = ttl_seconds or self.default_ttl
            lock_info = RoomLockInfo(
                room_id=room_id,
                selected_bot=bot,
                turn_id=turn_id,
                acquired_at=now,
                expires_at=now + timedelta(seconds=ttl),
            )
            self._locks[room_id] = lock_info

            logger.info(
                f"Turn lock ACQUIRED: Room '{room_id}' locked for {bot.value} (TTL: {ttl}s)",
                extra={"room_id": room_id, "bot": bot.value, "turn_id": turn_id}
            )
            return True

    async def release(
        self,
        room_id: str,
        bot: Optional[BotType] = None,
        turn_id: Optional[str] = None,
    ) -> bool:
        """
        Releases the room lock if held by the specified bot (or force release if bot is None).
        
        Returns:
            True if released, False if not held or held by another bot.
        """
        room_mutex = await self._get_room_mutex(room_id)
        async with room_mutex:
            existing = self._locks.get(room_id)
            if existing is None:
                return True

            if bot is not None and existing.selected_bot != bot:
                logger.warning(
                    f"Turn lock release rejected: Bot {bot.value} cannot release lock held by {existing.selected_bot.value}",
                    extra={"room_id": room_id}
                )
                return False

            # Prevent a cancelled/finished turn from releasing a newer turn's lock
            if turn_id is not None and existing.turn_id != turn_id:
                logger.warning(
                    f"Turn lock release rejected: turn {turn_id} cannot release lock held by turn {existing.turn_id}",
                    extra={"room_id": room_id}
                )
                return False

            del self._locks[room_id]
            logger.info(
                f"Turn lock RELEASED: Room '{room_id}' is now UNLOCKED",
                extra={"room_id": room_id}
            )
            return True

    async def is_locked(self, room_id: str) -> bool:
        """Checks if room is currently locked by an active, unexpired lock."""
        room_mutex = await self._get_room_mutex(room_id)
        async with room_mutex:
            existing = self._locks.get(room_id)
            if existing is None:
                return False
            if existing.is_expired:
                del self._locks[room_id]
                return False
            return True

    async def current_lock(self, room_id: str) -> Optional[RoomLockInfo]:
        """Returns metadata of active lock, if any."""
        room_mutex = await self._get_room_mutex(room_id)
        async with room_mutex:
            existing = self._locks.get(room_id)
            if existing is None:
                return None
            if existing.is_expired:
                del self._locks[room_id]
                return None
            return existing.model_copy()

    def reset_room(self, room_id: str) -> None:
        """Cleans up lock state for a room."""
        self._locks.pop(room_id, None)
        self._room_mutexes.pop(room_id, None)


# Global turn lock manager singleton
turn_lock_manager = TurnLockManager()
