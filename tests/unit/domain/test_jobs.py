from datetime import datetime, timedelta, timezone

import pytest

from talk_to_me_server.api.schemas import TextToSpeechRequest
from talk_to_me_server.domain.jobs import (
    InvalidTransition,
    Job,
    JobSnapshot,
    JobState,
    ValueState,
)


NOW = datetime(2026, 7, 18, 12, 0, tzinfo=timezone(timedelta(hours=2)))
def snapshot() -> JobSnapshot:
    return JobSnapshot(
        engine="Piper",
        speaker="en_US-ljspeech-medium",
        volume=100,
        workers=4,
    )


def test_request_limits_and_defaults() -> None:
    request = TextToSpeechRequest(values=["hello"])

    assert request.importance.value == "high"
    assert request.volume_multiplier == 1
    assert request.calculate_stats is False
    assert request.wait_until_playback_finished is False

    with pytest.raises(ValueError, match="255"):
        TextToSpeechRequest(values=["x"] * 256)
    with pytest.raises(ValueError, match="16384"):
        TextToSpeechRequest(values=["x" * 16_385])
    with pytest.raises(ValueError):
        TextToSpeechRequest()
    with pytest.raises(ValueError):
        TextToSpeechRequest(values=["hello"], importance="sometimes")
    with pytest.raises(ValueError):
        TextToSpeechRequest(values=["hello"], importance="must")
    with pytest.raises(ValueError):
        TextToSpeechRequest(values=["hello"], importance="could")
    with pytest.raises(ValueError):
        TextToSpeechRequest(values=["hello"], severity="info")


def test_volume_multiplier_clamps_and_requires_a_finite_number() -> None:
    assert TextToSpeechRequest(values=["x"], volume_multiplier=-1).volume_multiplier == 0
    assert TextToSpeechRequest(values=["x"], volume_multiplier=2).volume_multiplier == 1
    assert TextToSpeechRequest(values=["x"], volume_multiplier=0.25).volume_multiplier == 0.25
    with pytest.raises(ValueError, match="finite"):
        TextToSpeechRequest(values=["x"], volume_multiplier=float("nan"))


def test_request_accepts_exactly_one_of_value_and_values() -> None:
    singular = TextToSpeechRequest(value="One sentence. Another sentence.")

    assert singular.value == "One sentence. Another sentence."
    assert singular.values is None
    with pytest.raises(ValueError):
        TextToSpeechRequest(value="one", values=["two"])
    with pytest.raises(ValueError):
        TextToSpeechRequest(value=None)


def test_full_maximum_request_shape_is_valid() -> None:
    request = TextToSpeechRequest(values=["x" * 16_384 for _ in range(255)])

    assert len(request.values or []) == 255


def test_job_state_machine_rejects_invalid_transition() -> None:
    job = Job.from_request(
        "job-1",
        TextToSpeechRequest(values=["hello"]),
        snapshot(),
        at=NOW,
        monotonic_ns=0,
    )

    with pytest.raises(InvalidTransition):
        job.transition(JobState.PLAYING, at=NOW, monotonic_ns=1)


def test_job_transition_records_wall_and_monotonic_times() -> None:
    job = Job.from_request(
        "job-1",
        TextToSpeechRequest(values=["hello"]),
        snapshot(),
        at=NOW,
        monotonic_ns=0,
    )

    job.transition(JobState.PROCESSING, at=NOW, monotonic_ns=100_000_000)
    job.transition(JobState.PROCESSED, at=NOW, monotonic_ns=350_000_000)
    job.transition(JobState.PLAYING, at=NOW, monotonic_ns=400_000_000)
    job.transition(JobState.FINISHED, at=NOW, monotonic_ns=900_000_000)

    assert job.state is JobState.FINISHED
    assert job.processing_started_at == NOW
    assert job.processing_finished_at == NOW
    assert job.playback_started_at == NOW
    assert job.playback_finished_at == NOW
    assert job.monotonic_times["terminal"] == 900_000_000


def test_job_can_start_playback_before_all_synthesis_finishes() -> None:
    job = Job.from_request(
        "job-1",
        TextToSpeechRequest(values=["first", "second"]),
        snapshot(),
        at=NOW,
        monotonic_ns=0,
    )

    job.transition(JobState.PROCESSING, at=NOW, monotonic_ns=100_000_000)
    job.transition(JobState.PLAYING, at=NOW, monotonic_ns=200_000_000)
    job.mark_processing_finished(at=NOW, monotonic_ns=300_000_000)

    assert job.state is JobState.PLAYING
    assert job.processing_finished_at == NOW
    assert job.monotonic_times["processingFinished"] == 300_000_000


def test_value_transition_and_serialization_use_approved_names() -> None:
    job = Job.from_request(
        "job-1",
        TextToSpeechRequest(values=["hello"]),
        snapshot(),
        at=NOW,
        monotonic_ns=0,
    )
    value = job.values[0]

    value.transition(ValueState.PROCESSING, at=NOW, monotonic_ns=100_000_000)
    value.transition(ValueState.PROCESSED, at=NOW, monotonic_ns=300_000_000)

    serialized = job.to_dict()
    assert serialized["createdAt"] == "2026-07-18T12:00:00+02:00"
    assert "severity" not in serialized["snapshot"]
    assert "severityMode" not in serialized["snapshot"]
    assert serialized["values"][0]["id"] == "job-1-0"
    assert serialized["values"][0]["state"] == "processed"


def test_worker_metadata_is_serialized_only_when_requested() -> None:
    job = Job.from_request(
        "job-1",
        TextToSpeechRequest(values=["hello"]),
        snapshot(),
        at=NOW,
        monotonic_ns=0,
    )
    job.values[0].worker_index = 3

    assert "workerIndex" not in job.to_dict()["values"][0]
    detailed = job.to_dict(include_worker_details=True)
    assert "workerIndex" not in detailed
    assert "totalWorkers" not in detailed
    value = detailed["values"][0]
    assert list(value)[:4] == ["id", "index", "workerIndex", "totalWorkers"]
    assert value["workerIndex"] == 3
    assert value["totalWorkers"] == 4
