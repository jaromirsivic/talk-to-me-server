import json
from datetime import datetime, timedelta, timezone

from talk_to_me_server.api.schemas import TextToSpeechRequest
from talk_to_me_server.domain.jobs import Job, JobSnapshot, JobState
from talk_to_me_server.storage.archive import JobArchive


NOW = datetime(2026, 7, 18, 12, 0, tzinfo=timezone(timedelta(hours=2)))
SNAPSHOT = JobSnapshot(
    engine="Piper",
    speaker="en_US-ljspeech-medium",
    volume=100,
    workers=4,
)
PCM_WAV = b"RIFF\x04\x00\x00\x00WAVE"


def test_archive_contains_pretty_request_job_and_wavs(tmp_path) -> None:
    job = Job.from_request(
        "2026_07_18_12_00_00_0",
        TextToSpeechRequest(values=["hello"]),
        SNAPSHOT,
        at=NOW,
        monotonic_ns=0,
    )
    archive = JobArchive(tmp_path)

    archive.create(job)
    archive.write_value_wav(job.id, 0, PCM_WAV)
    job.transition(JobState.PROCESSING, at=NOW, monotonic_ns=1)
    job.transition(JobState.PROCESSED, at=NOW, monotonic_ns=2)
    job.transition(JobState.PLAYING, at=NOW, monotonic_ns=3)
    job.transition(JobState.FINISHED, at=NOW, monotonic_ns=4)
    archive.finalize(job)

    job_dir = tmp_path / job.id
    request_text = (job_dir / "request.json").read_text(encoding="utf-8")
    assert '\n  "values": [' in request_text
    assert json.loads(request_text)["values"] == ["hello"]
    assert json.loads((job_dir / "job.json").read_text(encoding="utf-8"))["state"] == (
        "finished"
    )
    assert (job_dir / "values" / "000.wav").read_bytes() == PCM_WAV


def test_archive_rejects_invalid_job_id(tmp_path) -> None:
    archive = JobArchive(tmp_path)

    try:
        archive.load("../outside")
    except ValueError as error:
        assert "job ID" in str(error)
    else:
        raise AssertionError("invalid job ID was accepted")
