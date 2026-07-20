from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from talk_to_me_server.api.schemas import Importance, TextToSpeechRequest
from talk_to_me_server.domain.ids import JobIdGenerator
from talk_to_me_server.domain.jobs import (
    Job,
    JobError,
    JobSnapshot,
    JobState,
    JobValue,
    ValueState,
)


LOW_BUSY_REASON = (
    "Message not processed. Queue is not empty and in that case low importance messages are not "
    "processed."
)


class ValueNotPlayable(RuntimeError):
    def __init__(self, job_id: str, index: int) -> None:
        super().__init__(f"value {index} of job {job_id} is not playable")
        self.job_id = job_id
        self.index = index


@dataclass(frozen=True)
class QueueSettingsSnapshot:
    engine: str
    speaker: str
    volume: int
    workers: int

    def for_job(
        self, importance: Importance, volume_multiplier: float = 1.0
    ) -> JobSnapshot:
        return JobSnapshot(
            engine=self.engine,
            speaker=self.speaker,
            volume=int(self.volume * volume_multiplier + 0.5),
            workers=self.workers,
            importance=importance,
        )


@dataclass(frozen=True)
class Admission:
    accepted: bool
    status: int
    reason: str
    job: Job | None = None


class QueueManager:
    def __init__(
        self,
        max_jobs: int,
        id_generator: JobIdGenerator,
        *,
        wall_clock: Callable[[], datetime] | None = None,
        monotonic_clock: Callable[[], int] | None = None,
    ) -> None:
        self._condition = asyncio.Condition()
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._max_jobs = max_jobs
        self._ids = id_generator
        self._wall_clock = wall_clock or (lambda: datetime.now().astimezone())
        self._monotonic_clock = monotonic_clock or time.monotonic_ns

    @property
    def active_count(self) -> int:
        return sum(not job.state.is_terminal for job in self._jobs.values())

    def active_ids(self) -> tuple[str, ...]:
        return tuple(job.id for job in self._jobs.values() if not job.state.is_terminal)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def enqueue(
        self, request: TextToSpeechRequest, snapshot: QueueSettingsSnapshot
    ) -> Admission:
        async with self._condition:
            if request.importance is Importance.LOW and self.active_count:
                return Admission(False, 200, LOW_BUSY_REASON)
            if self.active_count >= self._max_jobs:
                return Admission(False, 429, "Queue is full")
            wall_time = self._wall_clock()
            job_id = self._ids.next_id(wall_time)
            job = Job.from_request(
                job_id,
                request,
                snapshot.for_job(request.importance, request.volume_multiplier),
                at=wall_time,
                monotonic_ns=self._monotonic_clock(),
            )
            self._jobs[job.id] = job
            self._condition.notify_all()
            return Admission(True, 200, "OK", job)

    async def claim_for_synthesis(self, *, wait: bool = True) -> Job | None:
        async with self._condition:
            while True:
                claimable = self._next_for_synthesis()
                if claimable is not None:
                    claimable.transition(
                        JobState.PROCESSING,
                        at=self._wall_clock(),
                        monotonic_ns=self._monotonic_clock(),
                    )
                    self._condition.notify_all()
                    return claimable
                if not wait:
                    return None
                await self._condition.wait()

    def _next_for_synthesis(self) -> Job | None:
        for job in self._jobs.values():
            if (
                job.processing_started_at is not None
                and job.processing_finished_at is None
            ):
                return None
            if job.state is JobState.WAITING:
                return job
        return None

    async def mark_synthesis_finished(self, job_id: str) -> Job:
        async with self._condition:
            job = self._require(job_id)
            at = self._wall_clock()
            monotonic_ns = self._monotonic_clock()
            if job.state is JobState.PROCESSING:
                job.transition(
                    JobState.PROCESSED,
                    at=at,
                    monotonic_ns=monotonic_ns,
                )
            elif job.state is JobState.PLAYING:
                job.mark_processing_finished(at=at, monotonic_ns=monotonic_ns)
            self._condition.notify_all()
            return job

    async def record_synthesis_failure(self, job_id: str, error: JobError) -> Job:
        async with self._condition:
            job = self._require(job_id)
            if job.state.is_terminal:
                return job
            job.add_error(error)
            self._condition.notify_all()
            return job

    async def mark_synthesis_failed(self, job_id: str) -> Job:
        async with self._condition:
            job = self._require(job_id)
            if job.state.is_terminal:
                return job
            at = self._wall_clock()
            monotonic_ns = self._monotonic_clock()
            if job.state is JobState.PLAYING:
                job.mark_processing_finished(at=at, monotonic_ns=monotonic_ns)
            else:
                job.transition(
                    JobState.FAILED,
                    at=at,
                    monotonic_ns=monotonic_ns,
                )
            self._condition.notify_all()
            return job

    async def mark_value_processing(self, job_id: str, index: int) -> None:
        await self._transition_value(job_id, index, ValueState.PROCESSING)

    async def mark_value_processed(self, job_id: str, index: int) -> None:
        await self._transition_value(job_id, index, ValueState.PROCESSED)

    async def record_value_worker_index(
        self, job_id: str, value_index: int, worker_index: int
    ) -> None:
        async with self._condition:
            job = self._require(job_id)
            if not 0 <= worker_index < job.snapshot.workers:
                raise ValueError("worker index is outside the job worker range")
            try:
                value = job.values[value_index]
            except IndexError as error:
                raise IndexError(f"unknown value index: {value_index}") from error
            value.worker_index = worker_index
            self._condition.notify_all()

    async def mark_value_playing(self, job_id: str, index: int) -> None:
        await self._transition_value(job_id, index, ValueState.PLAYING)

    async def mark_value_finished(self, job_id: str, index: int) -> None:
        await self._transition_value(job_id, index, ValueState.FINISHED)

    async def mark_value_failed(self, job_id: str, index: int) -> None:
        await self._transition_value(job_id, index, ValueState.FAILED)

    async def wait_for_value(self, job_id: str, index: int) -> JobValue:
        async with self._condition:
            while True:
                job = self._require(job_id)
                try:
                    value = job.values[index]
                except IndexError as error:
                    raise IndexError(f"unknown value index: {index}") from error
                if value.state in {
                    ValueState.PROCESSED,
                    ValueState.PLAYING,
                    ValueState.FINISHED,
                }:
                    return value
                if value.state is ValueState.FAILED or job.state is JobState.FAILED:
                    raise ValueNotPlayable(job_id, index)
                await self._condition.wait()

    async def wait_synthesis_finished(self, job_id: str) -> Job:
        async with self._condition:
            while True:
                job = self._require(job_id)
                if job.processing_finished_at is not None or job.state.is_terminal:
                    return job
                await self._condition.wait()

    async def _transition_value(
        self, job_id: str, index: int, target: ValueState
    ) -> None:
        async with self._condition:
            job = self._require(job_id)
            try:
                value = job.values[index]
            except IndexError as error:
                raise IndexError(f"unknown value index: {index}") from error
            value.transition(
                target,
                at=self._wall_clock(),
                monotonic_ns=self._monotonic_clock(),
            )
            self._condition.notify_all()

    async def claim_for_playback(self, *, wait: bool = True) -> Job | None:
        async with self._condition:
            while True:
                claimable = self._next_for_playback()
                if claimable is not None:
                    claimable.transition(
                        JobState.PLAYING,
                        at=self._wall_clock(),
                        monotonic_ns=self._monotonic_clock(),
                    )
                    self._condition.notify_all()
                    return claimable
                if not wait:
                    return None
                await self._condition.wait()

    def _next_for_playback(self) -> Job | None:
        for job in self._jobs.values():
            if job.state.is_terminal:
                continue
            if job.state is JobState.PLAYING:
                return None
            if job.errors:
                return None
            first_value_ready = bool(
                job.values and job.values[0].state is ValueState.PROCESSED
            )
            if job.state is JobState.PROCESSED or (
                job.state is JobState.PROCESSING and first_value_ready
            ):
                return job
            return None
        return None

    async def finish(self, job_id: str) -> Job:
        async with self._condition:
            job = self._require(job_id)
            job.transition(
                JobState.FINISHED,
                at=self._wall_clock(),
                monotonic_ns=self._monotonic_clock(),
            )
            self._condition.notify_all()
            return job

    async def fail(self, job_id: str, error: JobError | None) -> Job:
        async with self._condition:
            job = self._require(job_id)
            job.transition(
                JobState.FAILED,
                at=self._wall_clock(),
                monotonic_ns=self._monotonic_clock(),
                error=error,
            )
            self._condition.notify_all()
            return job

    async def wait_terminal(self, job_id: str) -> Job:
        async with self._condition:
            while True:
                job = self._require(job_id)
                if job.state.is_terminal:
                    return job
                await self._condition.wait()

    async def release(self, job_id: str) -> None:
        async with self._condition:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if not job.state.is_terminal:
                raise RuntimeError("cannot release a nonterminal job")
            del self._jobs[job_id]
            self._condition.notify_all()

    def _require(self, job_id: str) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError as error:
            raise KeyError(f"unknown job: {job_id}") from error
