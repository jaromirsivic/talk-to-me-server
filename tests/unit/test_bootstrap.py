import json
import shutil
from pathlib import Path

import httpx
import pytest

from talk_to_me_server.bootstrap import bootstrap, refresh_official_catalog
from talk_to_me_server.lifespan import build_runtime


def test_bootstrap_copies_master_setup_and_preserves_user_setup(tmp_path: Path) -> None:
    first = bootstrap(tmp_path)
    setup_path = tmp_path / "data" / "setup.json"
    parsed = json.loads(setup_path.read_text(encoding="utf-8"))
    assert parsed["voice"]["speaker"] == "en_US-ljspeech-medium"
    parsed["voice"]["volume"] = 61
    setup_path.write_text(json.dumps(parsed), encoding="utf-8")

    second = bootstrap(tmp_path)

    assert json.loads(setup_path.read_text(encoding="utf-8"))["voice"]["volume"] == 61
    assert first.created is True
    assert second.created is False


def test_bootstrap_creates_project_local_roots_without_severity_gongs(tmp_path: Path) -> None:
    result = bootstrap(tmp_path)

    assert result.data_root == tmp_path / "data"
    assert not hasattr(result, "gong_paths")
    assert (tmp_path / "data" / "voices" / "official").is_dir()
    assert (tmp_path / "data" / "voices" / "custom").is_dir()


@pytest.mark.asyncio
async def test_catalog_refresh_reads_model_card_license_and_official_hashes(tmp_path) -> None:
    raw = {
        "cs_CZ-test-medium": {
            "name": "test",
            "language": {"code": "cs_CZ"},
            "quality": "medium",
            "files": {
                "cs/cs_CZ/test/medium/test.onnx": {
                    "size_bytes": 10,
                    "md5_digest": "model-md5",
                },
                "cs/cs_CZ/test/medium/test.onnx.json": {
                    "size_bytes": 10,
                    "md5_digest": "config-md5",
                },
                "cs/cs_CZ/test/medium/MODEL_CARD": {"size_bytes": 40},
            },
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        content = (
            json.dumps(raw).encode()
            if request.url.path.endswith("voices.json")
            else b"# Model card\n* License: CC0-1.0\n"
        )
        return httpx.Response(200, content=content, request=request)

    destination = tmp_path / "official.json"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await refresh_official_catalog(
            "https://voices.test/voices.json",
            "https://voices.test/",
            destination,
            http_client=client,
        )

    record = json.loads(destination.read_text(encoding="utf-8"))["voices"][0]
    assert record["license"] == "CC0-1.0"
    assert record["modelMd5"] == "model-md5"
    assert record["configMd5"] == "config-md5"


def test_build_runtime_wires_real_queue_voice_pool_playback_and_gc(tmp_path: Path) -> None:
    shutil.copytree(Path("master-data"), tmp_path / "master-data")

    runtime = build_runtime(tmp_path)

    assert runtime.queue is not None
    assert runtime.archive is not None
    assert runtime.process_pool is not None
    assert runtime.scheduler.pool is runtime.process_pool
    assert runtime.text_segmenter is not None
    assert runtime.playback is not None
    assert runtime.garbage_collector is not None
    assert runtime.voice_catalog.get("en_US-ljspeech-medium") is not None
