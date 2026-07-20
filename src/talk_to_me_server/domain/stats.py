from __future__ import annotations

from typing import Any

from talk_to_me_server.domain.jobs import Job, JobValue


def calculate_stats(job: Job) -> dict[str, Any]:
    processing_ms = _duration(
        job.monotonic_times.get("processingStarted"),
        job.monotonic_times.get("processingFinished"),
    )
    characters = sum(len(value.text) for value in job.values)
    return {
        "queueWaitMs": _duration(
            job.monotonic_times.get("created"),
            job.monotonic_times.get("processingStarted"),
        ),
        "processingDurationMs": processing_ms,
        "playbackDurationMs": _duration(
            job.monotonic_times.get("playbackStarted"),
            job.monotonic_times.get("playbackFinished"),
        ),
        "totalDurationMs": _duration(
            job.monotonic_times.get("created"),
            job.monotonic_times.get("terminal"),
        ),
        "characters": characters,
        "items": len(job.values),
        "charactersPerSecond": _throughput(characters, processing_ms),
        "engine": job.snapshot.engine,
        "speaker": job.snapshot.speaker,
        "workers": job.snapshot.workers,
        "perValue": [_value_stats(value) for value in job.values],
        "errors": [error.to_dict() for error in job.errors],
    }


def _value_stats(value: JobValue) -> dict[str, Any]:
    return {
        "index": value.index,
        "characters": len(value.text),
        "synthesisDurationMs": _duration(
            value.monotonic_times.get("processingStarted"),
            value.monotonic_times.get("processingFinished"),
        ),
        "playbackDurationMs": _duration(
            value.monotonic_times.get("playbackStarted"),
            value.monotonic_times.get("playbackFinished"),
        ),
        "state": value.state.value,
    }


def _duration(start: int | None, end: int | None) -> int | float | None:
    if start is None or end is None:
        return None
    milliseconds = (end - start) / 1_000_000
    return int(milliseconds) if milliseconds.is_integer() else round(milliseconds, 3)


def _throughput(characters: int, duration_ms: int | float | None) -> float | None:
    if duration_ms is None or duration_ms <= 0:
        return None
    return characters / (duration_ms / 1_000)
