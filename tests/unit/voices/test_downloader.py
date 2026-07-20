import hashlib
import json
from pathlib import Path

import httpx
import pytest

from talk_to_me_server.voices.catalog import VoiceCatalog
from talk_to_me_server.voices.downloader import (
    ChecksumMismatch,
    DownloadTooLarge,
    LicenseRestricted,
    VoiceDownloadError,
    VoiceDownloader,
)
from talk_to_me_server.voices.licenses import VoiceLicensePolicy
from talk_to_me_server.voices.models import VoiceStatus


MODEL = b"valid-model"
CONFIG = json.dumps({"audio": {"sample_rate": 22050}}).encode()


def make_catalog(
    tmp_path: Path, model_hash: str, license_name: str = "Public Domain"
) -> VoiceCatalog:
    official = tmp_path / "official.json"
    official.write_text(
        json.dumps(
            {
                "voices": [
                    {
                        "id": "en_US-ljspeech-medium",
                        "name": "LJSpeech",
                        "language": "en-US",
                        "quality": "medium",
                        "license": license_name,
                        "modelUrl": "https://voices.test/model.onnx",
                        "configUrl": "https://voices.test/model.onnx.json",
                        "modelSha256": model_hash,
                        "configSha256": hashlib.sha256(CONFIG).hexdigest(),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    policy = VoiceLicensePolicy.from_file(Path("master-data/voice-license-policy.json"))
    return VoiceCatalog(official, tmp_path / "installed", tmp_path / "custom", policy)


def make_client(model: bytes = MODEL) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = model if request.url.path.endswith(".onnx") else CONFIG
        return httpx.Response(200, content=body, request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_download_activates_pair_only_after_hash_and_validation(tmp_path) -> None:
    catalog = make_catalog(tmp_path, hashlib.sha256(MODEL).hexdigest())
    validated = []
    async with make_client() as http_client:
        downloader = VoiceDownloader(
            catalog,
            tmp_path / "installed",
            http_client,
            validator=lambda model, config: validated.append((model, config)),
        )
        voice = await downloader.download("en_US-ljspeech-medium")

    destination = tmp_path / "installed" / "en_US-ljspeech-medium"
    assert voice.status.value == "ready"
    assert (destination / "model.onnx").read_bytes() == MODEL
    assert json.loads((destination / "model.onnx.json").read_text(encoding="utf-8"))
    assert json.loads((destination / "voice.json").read_text(encoding="utf-8"))["licenseDecision"] == "approved"
    assert validated
    assert not list((tmp_path / "installed").glob(".staging-*"))


@pytest.mark.asyncio
async def test_restricted_download_requires_explicit_confirmation(tmp_path) -> None:
    catalog = make_catalog(
        tmp_path, hashlib.sha256(MODEL).hexdigest(), license_name="CC-BY-NC-4.0"
    )
    async with make_client() as client:
        downloader = VoiceDownloader(catalog, tmp_path / "installed", client, lambda *_: None)
        with pytest.raises(LicenseRestricted):
            await downloader.download("en_US-ljspeech-medium")
        voice = await downloader.download(
            "en_US-ljspeech-medium", license_confirmed=True
        )
    assert voice.status is VoiceStatus.READY
    destination = tmp_path / "installed" / "en_US-ljspeech-medium"
    assert json.loads((destination / "voice.json").read_text(encoding="utf-8"))["licenseDecision"] == "confirmed"


@pytest.mark.asyncio
async def test_incomplete_catalog_voice_is_unavailable_not_license_restricted(
    tmp_path,
) -> None:
    catalog = make_catalog(tmp_path, hashlib.sha256(MODEL).hexdigest())
    data = json.loads(catalog.official_cache.read_text(encoding="utf-8"))
    data["voices"][0].pop("configUrl")
    catalog.official_cache.write_text(json.dumps(data), encoding="utf-8")

    async with make_client() as client:
        downloader = VoiceDownloader(
            catalog, tmp_path / "installed", client, lambda *_: None
        )
        with pytest.raises(VoiceDownloadError, match="metadata") as caught:
            await downloader.download("en_US-ljspeech-medium")
    assert type(caught.value).__name__ == "VoiceUnavailable"


@pytest.mark.asyncio
async def test_hash_mismatch_leaves_no_active_or_staging_voice(tmp_path) -> None:
    catalog = make_catalog(tmp_path, hashlib.sha256(b"expected").hexdigest())
    async with make_client(model=b"corrupt") as http_client:
        downloader = VoiceDownloader(
            catalog,
            tmp_path / "installed",
            http_client,
            validator=lambda *_: None,
        )
        with pytest.raises(ChecksumMismatch):
            await downloader.download("en_US-ljspeech-medium")

    assert not (tmp_path / "installed" / "en_US-ljspeech-medium").exists()
    assert not list((tmp_path / "installed").glob(".staging-*"))


@pytest.mark.asyncio
async def test_download_rejects_non_http_url_without_residue(tmp_path) -> None:
    catalog = make_catalog(tmp_path, hashlib.sha256(MODEL).hexdigest())
    data = json.loads(catalog.official_cache.read_text(encoding="utf-8"))
    data["voices"][0]["modelUrl"] = "file:///private/model.onnx"
    catalog.official_cache.write_text(json.dumps(data), encoding="utf-8")
    async with make_client() as http_client:
        downloader = VoiceDownloader(catalog, tmp_path / "installed", http_client, lambda *_: None)
        with pytest.raises(VoiceDownloadError):
            await downloader.download("en_US-ljspeech-medium")

    assert not list((tmp_path / "installed").glob(".staging-*"))


@pytest.mark.asyncio
async def test_streaming_limit_applies_without_content_length(tmp_path, monkeypatch) -> None:
    catalog = make_catalog(tmp_path, hashlib.sha256(MODEL).hexdigest())
    monkeypatch.setattr("talk_to_me_server.voices.downloader.MODEL_LIMIT", 3)
    async with make_client() as http_client:
        downloader = VoiceDownloader(catalog, tmp_path / "installed", http_client, lambda *_: None)
        with pytest.raises(DownloadTooLarge):
            await downloader.download("en_US-ljspeech-medium")

    assert not list((tmp_path / "installed").glob(".staging-*"))


@pytest.mark.asyncio
async def test_timeout_is_mapped_to_download_error_and_cleans_staging(tmp_path) -> None:
    catalog = make_catalog(tmp_path, hashlib.sha256(MODEL).hexdigest())

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as http_client:
        downloader = VoiceDownloader(catalog, tmp_path / "installed", http_client, lambda *_: None)
        with pytest.raises(VoiceDownloadError):
            await downloader.download("en_US-ljspeech-medium")

    assert not list((tmp_path / "installed").glob(".staging-*"))


@pytest.mark.asyncio
async def test_official_md5_metadata_is_verified_when_sha256_is_unavailable(tmp_path) -> None:
    catalog = make_catalog(tmp_path, hashlib.sha256(MODEL).hexdigest())
    data = json.loads(catalog.official_cache.read_text(encoding="utf-8"))
    record = data["voices"][0]
    record.pop("modelSha256")
    record.pop("configSha256")
    record["modelMd5"] = hashlib.md5(MODEL).hexdigest()  # noqa: S324 - official catalog format
    record["configMd5"] = hashlib.md5(CONFIG).hexdigest()  # noqa: S324
    catalog.official_cache.write_text(json.dumps(data), encoding="utf-8")

    async with make_client() as http_client:
        voice = await VoiceDownloader(
            catalog, tmp_path / "installed", http_client, lambda *_: None
        ).download("en_US-ljspeech-medium")

    assert voice.status.value == "ready"
