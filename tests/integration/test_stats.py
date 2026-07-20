from datetime import datetime, timezone

from talk_to_me_server.api.schemas import TextToSpeechRequest
from talk_to_me_server.domain.jobs import Job, JobSnapshot, JobState, ValueState
from talk_to_me_server.domain.stats import calculate_stats


def test_stats_include_complete_per_value_shape_and_partial_nulls() -> None:
    now = datetime(2026, 7, 18, tzinfo=timezone.utc)
    snapshot = JobSnapshot(
        engine="Piper",
        speaker="en_US-ljspeech-medium",
        volume=100,
        workers=4,
    )
    job = Job.from_request(
        "job-1",
        TextToSpeechRequest(values=["abc", "later"]),
        snapshot,
        at=now,
        monotonic_ns=0,
    )
    job.transition(JobState.PROCESSING, at=now, monotonic_ns=100_000_000)
    job.values[0].transition(ValueState.PROCESSING, at=now, monotonic_ns=120_000_000)
    job.values[0].transition(ValueState.PROCESSED, at=now, monotonic_ns=220_000_000)
    job.transition(JobState.FAILED, at=now, monotonic_ns=350_000_000)

    stats = calculate_stats(job)

    assert stats["processingDurationMs"] == 250
    assert stats["perValue"][0] == {
        "index": 0,
        "characters": 3,
        "synthesisDurationMs": 100,
        "playbackDurationMs": None,
        "state": "processed",
    }
    assert stats["perValue"][1]["synthesisDurationMs"] is None
    assert stats["perValue"][1]["playbackDurationMs"] is None
