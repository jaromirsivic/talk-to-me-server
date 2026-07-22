from __future__ import annotations

from collections.abc import AsyncIterable, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class PlaybackValue:
    index: int
    path: Path


PlaybackCallback = Callable[[int], Awaitable[None]]


class AudioPlayer(Protocol):
    async def play(
        self,
        values: AsyncIterable[PlaybackValue],
        volume: int,
        on_started: PlaybackCallback,
        on_finished: PlaybackCallback,
    ) -> None: ...

    async def stop(self) -> None: ...
