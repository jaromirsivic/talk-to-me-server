from pathlib import Path

from starlette.testclient import TestClient

from talk_to_me_server.app import create_app
from talk_to_me_server.config.models import Settings
from talk_to_me_server.config.service import SettingsService
from talk_to_me_server.domain.ids import JobIdGenerator
from talk_to_me_server.domain.queue import QueueManager
from talk_to_me_server.lifespan import Runtime
from talk_to_me_server.storage.archive import JobArchive


def paused_runtime(tmp_path: Path, settings: Settings) -> Runtime:
    service = SettingsService(tmp_path / "setup.json", settings)
    service.initialize()
    archive = JobArchive(tmp_path / "archive")
    return Runtime(
        settings=service,
        startup_settings=service.current(),
        queue=QueueManager(100, JobIdGenerator(archive.root)),
        archive=archive,
    )


def test_maximum_255_by_16384_shape_is_admitted(
    tmp_path: Path, approved_settings: Settings
) -> None:
    runtime = paused_runtime(tmp_path, approved_settings)
    payload = {"values": ["x" * 16_384 for _ in range(255)]}

    with TestClient(create_app(runtime), client=("127.0.0.1", 50_000)) as client:
        response = client.post("/api/v1/textToSpeech", json=payload)

    assert response.status_code == 200
    assert response.json()["jobId"]
    assert runtime.queue.active_count == 1


def test_job_101_is_rejected_while_one_hundred_are_active(
    tmp_path: Path, approved_settings: Settings
) -> None:
    runtime = paused_runtime(tmp_path, approved_settings)

    with TestClient(create_app(runtime), client=("127.0.0.1", 50_000)) as client:
        for _ in range(100):
            response = client.post("/api/v1/textToSpeech", json={"values": ["x"]})
            assert response.status_code == 200
        overflow = client.post(
            "/api/v1/textToSpeech", json={"values": ["overflow"]}
        )

    assert overflow.status_code == overflow.json()["reasonCode"] == 429
    assert runtime.queue.active_count == 100
