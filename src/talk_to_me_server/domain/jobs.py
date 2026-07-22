from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from talk_to_me_server.api.schemas import Importance, TextToSpeechRequest


class InvalidTransition(ValueError):
    pass


class JobState(StrEnum):
    WAITING = "waiting"
    PROCESSING = "processing"
    PROCESSED = "processed"
    PLAYING = "playing"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {self.FINISHED, self.FAILED, self.CANCELLED}


class ValueState(StrEnum):
    WAITING = "waiting"
    PROCESSING = "processing"
    PROCESSED = "processed"
    PLAYING = "playing"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {self.FINISHED, self.FAILED, self.CANCELLED}


JOB_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.WAITING: {JobState.PROCESSING, JobState.FAILED, JobState.CANCELLED},
    JobState.PROCESSING: {
        JobState.PROCESSED,
        JobState.PLAYING,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.PROCESSED: {JobState.PLAYING, JobState.FAILED, JobState.CANCELLED},
    JobState.PLAYING: {JobState.FINISHED, JobState.FAILED, JobState.CANCELLED},
    JobState.FINISHED: set(),
    JobState.FAILED: set(),
    JobState.CANCELLED: set(),
}

VALUE_TRANSITIONS: dict[ValueState, set[ValueState]] = {
    ValueState.WAITING: {ValueState.PROCESSING, ValueState.FAILED, ValueState.CANCELLED},
    ValueState.PROCESSING: {
        ValueState.PROCESSED,
        ValueState.FAILED,
        ValueState.CANCELLED,
    },
    ValueState.PROCESSED: {ValueState.PLAYING, ValueState.FAILED, ValueState.CANCELLED},
    ValueState.PLAYING: {ValueState.FINISHED, ValueState.FAILED, ValueState.CANCELLED},
    ValueState.FINISHED: set(),
    ValueState.FAILED: set(),
    ValueState.CANCELLED: set(),
}


@dataclass(frozen=True)
class JobSnapshot:
    engine: str
    speaker: str
    volume: int
    workers: int
    importance: Importance = Importance.HIGH

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "speaker": self.speaker,
            "volume": self.volume,
            "importance": self.importance.value,
            "workers": self.workers,
        }


@dataclass(frozen=True)
class JobError:
    code: int
    message: str
    component: str | None = None
    value_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "component": self.component,
            "valueIndex": self.value_index,
        }


@dataclass
class JobValue:
    id: str
    index: int
    text: str
    worker_index: int | None = None
    state: ValueState = ValueState.WAITING
    processing_started_at: datetime | None = None
    processing_finished_at: datetime | None = None
    playback_started_at: datetime | None = None
    playback_finished_at: datetime | None = None
    monotonic_times: dict[str, int] = field(default_factory=dict, repr=False)

    def transition(self, target: ValueState, *, at: datetime, monotonic_ns: int) -> None:
        if target not in VALUE_TRANSITIONS[self.state]:
            raise InvalidTransition(f"value cannot transition from {self.state} to {target}")
        self.state = target
        if target is ValueState.PROCESSING:
            self.processing_started_at = at
            self.monotonic_times["processingStarted"] = monotonic_ns
        elif target is ValueState.PROCESSED:
            self.processing_finished_at = at
            self.monotonic_times["processingFinished"] = monotonic_ns
        elif target is ValueState.PLAYING:
            self.playback_started_at = at
            self.monotonic_times["playbackStarted"] = monotonic_ns
        elif target is ValueState.FINISHED:
            self.playback_finished_at = at
            self.monotonic_times["playbackFinished"] = monotonic_ns
            self.monotonic_times["terminal"] = monotonic_ns
        elif target in {ValueState.FAILED, ValueState.CANCELLED}:
            self._record_failure(at, monotonic_ns)

    def _record_failure(self, at: datetime, monotonic_ns: int) -> None:
        if "processingStarted" in self.monotonic_times and "processingFinished" not in self.monotonic_times:
            self.processing_finished_at = at
            self.monotonic_times["processingFinished"] = monotonic_ns
        if "playbackStarted" in self.monotonic_times and "playbackFinished" not in self.monotonic_times:
            self.playback_finished_at = at
            self.monotonic_times["playbackFinished"] = monotonic_ns
        self.monotonic_times["terminal"] = monotonic_ns

    def to_dict(
        self,
        *,
        include_worker_details: bool = False,
        total_workers: int | None = None,
    ) -> dict[str, Any]:
        result = {
            "id": self.id,
            "index": self.index,
        }
        if include_worker_details:
            result.update(
                workerIndex=self.worker_index,
                totalWorkers=total_workers,
            )
        result.update({
            "text": self.text,
            "state": self.state.value,
            "processingStartedAt": _iso(self.processing_started_at),
            "processingFinishedAt": _iso(self.processing_finished_at),
            "playbackStartedAt": _iso(self.playback_started_at),
            "playbackFinishedAt": _iso(self.playback_finished_at),
        })
        return result


@dataclass
class Job:
    id: str
    created_at: datetime
    state: JobState
    request: TextToSpeechRequest
    snapshot: JobSnapshot
    values: list[JobValue]
    processing_started_at: datetime | None = None
    processing_finished_at: datetime | None = None
    playback_started_at: datetime | None = None
    playback_finished_at: datetime | None = None
    errors: list[JobError] = field(default_factory=list)
    monotonic_times: dict[str, int] = field(default_factory=dict, repr=False)

    @classmethod
    def from_request(
        cls,
        job_id: str,
        request: TextToSpeechRequest,
        snapshot: JobSnapshot,
        *,
        at: datetime,
        monotonic_ns: int,
    ) -> Job:
        if at.utcoffset() is None:
            raise ValueError("job time must be timezone-aware")
        values = [
            JobValue(id=f"{job_id}-{index}", index=index, text=text)
            for index, text in enumerate(request.values or [])
        ]
        return cls(
            id=job_id,
            created_at=at,
            state=JobState.WAITING,
            request=request.model_copy(deep=True),
            snapshot=snapshot,
            values=values,
            monotonic_times={"created": monotonic_ns},
        )

    def transition(
        self,
        target: JobState,
        *,
        at: datetime,
        monotonic_ns: int,
        error: JobError | None = None,
    ) -> None:
        if target not in JOB_TRANSITIONS[self.state]:
            raise InvalidTransition(f"job cannot transition from {self.state} to {target}")
        self.state = target
        if target is JobState.PROCESSING:
            self.processing_started_at = at
            self.monotonic_times["processingStarted"] = monotonic_ns
        elif target is JobState.PROCESSED:
            self.mark_processing_finished(at=at, monotonic_ns=monotonic_ns)
        elif target is JobState.PLAYING:
            self.playback_started_at = at
            self.monotonic_times["playbackStarted"] = monotonic_ns
        elif target is JobState.FINISHED:
            self.playback_finished_at = at
            self.monotonic_times["playbackFinished"] = monotonic_ns
            self.monotonic_times["terminal"] = monotonic_ns
        elif target in {JobState.FAILED, JobState.CANCELLED}:
            self._record_failure(at, monotonic_ns)
        if error is not None:
            self.add_error(error)

    def mark_processing_finished(self, *, at: datetime, monotonic_ns: int) -> None:
        if self.processing_finished_at is None:
            self.processing_finished_at = at
            self.monotonic_times["processingFinished"] = monotonic_ns

    def add_error(self, error: JobError) -> None:
        if error not in self.errors:
            self.errors.append(error)

    def _record_failure(self, at: datetime, monotonic_ns: int) -> None:
        if "processingStarted" in self.monotonic_times and "processingFinished" not in self.monotonic_times:
            self.mark_processing_finished(at=at, monotonic_ns=monotonic_ns)
        if "playbackStarted" in self.monotonic_times and "playbackFinished" not in self.monotonic_times:
            self.playback_finished_at = at
            self.monotonic_times["playbackFinished"] = monotonic_ns
        self.monotonic_times["terminal"] = monotonic_ns

    def to_dict(self, *, include_worker_details: bool = False) -> dict[str, Any]:
        return {
            "id": self.id,
            "createdAt": self.created_at.isoformat(),
            "state": self.state.value,
            "processingStartedAt": _iso(self.processing_started_at),
            "processingFinishedAt": _iso(self.processing_finished_at),
            "playbackStartedAt": _iso(self.playback_started_at),
            "playbackFinishedAt": _iso(self.playback_finished_at),
            "snapshot": self.snapshot.to_dict(),
            "values": [
                value.to_dict(
                    include_worker_details=include_worker_details,
                    total_workers=self.snapshot.workers,
                )
                for value in self.values
            ],
            "errors": [error.to_dict() for error in self.errors],
        }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
