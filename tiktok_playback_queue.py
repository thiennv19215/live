"""FIFO playback queue and immutable playback job model."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GiftJob:
    gift_name: str
    file_path: Path
    priority: int = 1  # Kept for configuration-file compatibility; FIFO ignores it.
    sound_path: Path | None = None
    target_char: str = "main"
    sender: str = "Người xem"
    repeat_count: int = 1
    diamonds: int = 0
    timestamp: str = ""
    event_type: str = "gift"
    event_value: str = ""
    history_id: str = ""


class FifoPlaybackQueue:
    """Events are always played in the same order they are received."""

    def __init__(self) -> None:
        self._items: deque[GiftJob] = deque()
        self._condition = asyncio.Condition()

    async def put(self, job: GiftJob) -> None:
        async with self._condition:
            self._items.append(job)
            self._condition.notify()

    async def get(self) -> GiftJob:
        async with self._condition:
            await self._condition.wait_for(lambda: bool(self._items))
            return self._items.popleft()

    def clear(self) -> int:
        count = len(self._items)
        self._items.clear()
        return count

    async def drain_async(self) -> list[GiftJob]:
        """Remove and return pending jobs so callers can update their lifecycle."""
        async with self._condition:
            items = list(self._items)
            self._items.clear()
            return items

    def get_items(self) -> list[GiftJob]:
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)
