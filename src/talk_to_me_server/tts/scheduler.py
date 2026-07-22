from __future__ import annotations

import asyncio
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from talk_to_me_server.domain.jobs import Job, JobError
from talk_to_me_server.domain.queue import JobCancelled, QueueManager
from talk_to_me_server.storage.archive import JobArchive
from talk_to_me_server.tts.base import SynthesisCommand, SynthesisPool
from talk_to_me_server.tts.pauses import PauseCommand, silence_wav
from talk_to_me_server.tts.sounds import (
    PlayCommand,
    SoundCommandError,
    SoundLibrary,
    SoundNotFoundError,
)


class ValueSynthesisError(RuntimeError):
    def __init__(self, index: int, cause: BaseException) -> None:
        super().__init__(str(cause))
        self.index = index
        self.cause = cause


class SynthesisScheduler:
    def __init__(
        self,
        queue: QueueManager,
        archive: JobArchive,
        pool: SynthesisPool,
        *,
        sound_directory: Path | None = None,
    ) -> None:
        self.queue = queue
        self.archive = archive
        self.pool = pool
        self.sounds = SoundLibrary(sound_directory) if sound_directory is not None else None

    async def run(self) -> None:
        while True:
            job = await self.queue.claim_for_synthesis()
            if job is not None:
                await self._process(job)

    async def _process(self, job: Job) -> None:
        results = await asyncio.gather(
            *(self._synthesize_value(job, index) for index in range(len(job.values))),
            return_exceptions=True,
        )
        failure = next((result for result in results if isinstance(result, BaseException)), None)
        if isinstance(failure, JobCancelled):
            return
        if failure is not None:
            current = await self.queue.mark_synthesis_failed(job.id)
            if current.state.is_terminal:
                self.archive.finalize(current)
                if not _client_waits(current):
                    await self.queue.release(current.id)
            return
        await self.queue.mark_synthesis_finished(job.id)

    async def _synthesize_value(self, job: Job, index: int) -> None:
        value = job.values[index]
        await self.queue.mark_value_processing(job.id, index)
        pause = PauseCommand.from_text(value.text)
        play = PlayCommand.from_text(value.text)
        command = SynthesisCommand(
            job_id=job.id,
            index=index,
            text=value.text,
            speaker=job.snapshot.speaker,
            output_path=self.archive.value_path(job.id, index),
        )
        try:
            if pause is not None:
                await self._materialize_pause(
                    job.id,
                    index,
                    pause.duration_ms if pause.duration_ms is not None else 0,
                )
            elif play is None:
                result = await self.pool.synthesize(command)
                if (
                    result.output_path != command.output_path
                    or not command.output_path.is_file()
                ):
                    raise RuntimeError("synthesis did not produce the requested WAV")
                await self.queue.record_value_worker_index(
                    job.id, index, result.worker_index
                )
            else:
                try:
                    await self._materialize_sound(job.id, index, play)
                except SoundNotFoundError:
                    await self._materialize_pause(job.id, index, 0)
        except BaseException as error:
            if isinstance(error, asyncio.CancelledError):
                raise
            await self.queue.mark_value_failed(job.id, index)
            await self.queue.record_synthesis_failure(
                job.id, _synthesis_error(error, index)
            )
            raise ValueSynthesisError(index, error) from error
        await self.queue.mark_value_processed(job.id, index)

    async def _materialize_sound(
        self, job_id: str, index: int, command: PlayCommand
    ) -> None:
        if self.sounds is None:
            raise SoundCommandError("Sound directory is not configured")
        data = await asyncio.to_thread(self.sounds.load, command.filename)
        await asyncio.to_thread(self.archive.write_value_wav, job_id, index, data)

    async def _materialize_pause(
        self, job_id: str, index: int, duration_ms: int
    ) -> None:
        data = await asyncio.to_thread(silence_wav, duration_ms)
        await asyncio.to_thread(self.archive.write_value_wav, job_id, index, data)


def _synthesis_error(cause: BaseException, index: int) -> JobError:
    if isinstance(cause, SoundCommandError):
        return JobError(
            code=404 if isinstance(cause, SoundNotFoundError) else 400,
            message=str(cause),
            component="sound",
            value_index=index,
        )
    unavailable = isinstance(cause, (BrokenProcessPool, TimeoutError))
    return JobError(
        code=503 if unavailable else 500,
        message=(
            "Speech synthesis workers are unavailable"
            if unavailable
            else "Speech synthesis failed"
        ),
        component="synthesis",
        value_index=index,
    )


def _client_waits(job: Job) -> bool:
    return job.request.calculate_stats or job.request.wait_until_playback_finished
