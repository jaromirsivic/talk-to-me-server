from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from talk_to_me_server.domain.jobs import Job, JobError, JobState
from talk_to_me_server.domain.queue import JobCancelled, QueueManager, ValueNotPlayable
from talk_to_me_server.playback.base import AudioPlayer, PlaybackValue
from talk_to_me_server.storage.archive import JobArchive
from talk_to_me_server.tts.pauses import PauseCommand


LOGGER = logging.getLogger("talk_to_me_server")


class PlaybackCoordinator:
    def __init__(
        self,
        queue: QueueManager,
        archive: JobArchive,
        player: AudioPlayer,
        *,
        retry_delay: float = 0.05,
    ) -> None:
        self.queue = queue
        self.archive = archive
        self.player = player
        self.retry_delay = retry_delay

    async def run(self) -> None:
        while True:
            job = await self.queue.claim_for_playback()
            if job is not None:
                await self._play(job)

    async def _play(self, job: Job) -> None:
        try:
            await self._play_with_retry(job)
            current = await self.queue.wait_synthesis_finished(job.id)
            if current.state is JobState.CANCELLED:
                return
            terminal = await self.queue.finish(job.id)
        except JobCancelled:
            return
        except ValueNotPlayable:
            current = await self.queue.wait_synthesis_finished(job.id)
            if current.state.is_terminal:
                terminal = current
            else:
                error = None if current.errors else JobError(
                    code=500,
                    message="Speech synthesis failed",
                    component="synthesis",
                )
                terminal = await self.queue.fail(job.id, error)
        except BaseException as error:
            if isinstance(error, asyncio.CancelledError):
                raise
            terminal = await self.queue.fail(
                job.id,
                JobError(
                    code=503,
                    message="Audio playback unavailable",
                    component="playback",
                ),
            )
        if terminal.state is JobState.CANCELLED:
            return
        self.archive.finalize(terminal)
        if not _client_waits(terminal):
            await self.queue.release(terminal.id)

    async def _play_with_retry(self, job: Job) -> None:
        for attempt in range(1, 4):
            started = False

            async def on_started(index: int) -> None:
                nonlocal started
                started = True
                await self.queue.mark_value_playing(job.id, index)

            async def on_finished(index: int) -> None:
                await self.queue.mark_value_finished(job.id, index)

            try:
                await self.player.play(
                    self._ready_values(job),
                    job.snapshot.volume,
                    on_started,
                    on_finished,
                )
                return
            except asyncio.CancelledError:
                raise
            except ValueNotPlayable:
                raise
            except Exception:
                LOGGER.warning(
                    "Audio playback attempt failed",
                    exc_info=True,
                    extra={
                        "component": "playback",
                        "event": "audio.retry",
                        "value_index": attempt,
                    },
                )
                if started or attempt == 3:
                    raise
                await asyncio.sleep(self.retry_delay)

    async def _ready_values(self, job: Job) -> AsyncIterator[PlaybackValue]:
        for value in job.values:
            await self.queue.wait_for_value(job.id, value.index)
            pause = PauseCommand.from_text(value.text)
            if pause is not None and not pause.duration_ms:
                await self.queue.mark_value_playing(job.id, value.index)
                await self.queue.mark_value_finished(job.id, value.index)
                continue
            yield PlaybackValue(
                index=value.index,
                path=self.archive.value_path(job.id, value.index),
            )

    async def stop(self) -> None:
        stop_player = getattr(self.player, "stop", None)
        if stop_player is not None:
            await stop_player()


def _client_waits(job: Job) -> bool:
    return job.request.calculate_stats or job.request.wait_until_playback_finished
