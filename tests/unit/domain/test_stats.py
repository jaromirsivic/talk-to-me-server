from datetime import datetime, timedelta, timezone

import pytest

from talk_to_me_server.api.schemas import TextToSpeechRequest
from talk_to_me_server.domain.jobs import Job, JobError, JobSnapshot, JobState
from talk_to_me_server.domain.stats import calculate_stats


NOW = datetime(2026, 7, 18, 12, 0, tzinfo=timezone(timedelta(hours=2)))
SNAPSHOT = JobSnapshot(
    engine="Piper",
    speaker="en_US-ljspeech-medium",
    volume=100,
    workers=4,
)


def test_stats_derive_from_monotonic_intervals() -> None:
    job = Job.from_request(
        "job-1",
        TextToSpeechRequest(values=["hello", "world"]),
        SNAPSHOT,
        at=NOW,
        monotonic_ns=0,
    )
    job.transition(JobState.PROCESSING, at=NOW, monotonic_ns=100_000_000)
    job.transition(JobState.PROCESSED, at=NOW, monotonic_ns=600_000_000)
    job.transition(JobState.PLAYING, at=NOW, monotonic_ns=700_000_000)
    job.transition(JobState.FINISHED, at=NOW, monotonic_ns=1_200_000_000)

    stats = calculate_stats(job)

    assert stats["queueWaitMs"] == 100
    assert stats["processingDurationMs"] == 500
    assert stats["playbackDurationMs"] == 500
    assert stats["totalDurationMs"] == 1_200
    assert stats["characters"] == 10
    assert stats["items"] == 2
    assert stats["charactersPerSecond"] == pytest.approx(20.0)
    assert stats["engine"] == "Piper"
    assert stats["speaker"] == "en_US-ljspeech-medium"
    assert stats["workers"] == 4


def test_failed_job_exposes_partial_stats_and_error() -> None:
    job = Job.from_request(
        "job-1",
        TextToSpeechRequest(values=["hello"]),
        SNAPSHOT,
        at=NOW,
        monotonic_ns=0,
    )
    job.transition(JobState.PROCESSING, at=NOW, monotonic_ns=100_000_000)
    job.transition(
        JobState.FAILED,
        at=NOW,
        monotonic_ns=300_000_000,
        error=JobError(code=500, message="Piper failed", component="synthesis", value_index=0),
    )

    stats = calculate_stats(job)

    assert stats["queueWaitMs"] == 100
    assert stats["processingDurationMs"] == 200
    assert stats["playbackDurationMs"] is None
    assert stats["totalDurationMs"] == 300
    assert stats["errors"][0]["valueIndex"] == 0
