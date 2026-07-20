import hashlib
import json
from pathlib import Path

import httpx

from talk_to_me_server.voices.catalog import VoiceCatalog
from talk_to_me_server.voices.deleter import VoiceDeleter
from talk_to_me_server.voices.downloader import VoiceDownloader
from talk_to_me_server.voices.importer import VoiceImporter
from talk_to_me_server.voices.licenses import VoiceLicensePolicy


MODEL = b"voice-model"
CONFIG = json.dumps({"audio": {"sample_rate": 22_050}}).encode()


def configure_voice_services(runtime, tmp_path: Path) -> None:
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
                        "license": "Public Domain",
                        "modelUrl": "https://voices.test/model.onnx",
                        "configUrl": "https://voices.test/model.onnx.json",
                        "modelSha256": hashlib.sha256(MODEL).hexdigest(),
                        "configSha256": hashlib.sha256(CONFIG).hexdigest(),
                    },
                    {
                        "id": "en_US-restricted-medium",
                        "name": "Restricted LJSpeech",
                        "language": "en-US",
                        "quality": "medium",
                        "license": "CC-BY-NC-4.0",
                        "modelUrl": "https://voices.test/restricted.onnx",
                        "configUrl": "https://voices.test/restricted.onnx.json",
                        "modelSha256": hashlib.sha256(MODEL).hexdigest(),
                        "configSha256": hashlib.sha256(CONFIG).hexdigest(),
                    },
                    {
                        "id": "en_US-incomplete-medium",
                        "name": "Incomplete LJSpeech",
                        "language": "en-US",
                        "quality": "medium",
                        "license": "Public Domain",
                        "modelUrl": "https://voices.test/incomplete.onnx",
                        "modelSha256": hashlib.sha256(MODEL).hexdigest(),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    policy = VoiceLicensePolicy.from_file(Path("master-data/voice-license-policy.json"))
    runtime.voice_catalog = VoiceCatalog(
        official, tmp_path / "installed", tmp_path / "custom", policy
    )

    def handler(request: httpx.Request) -> httpx.Response:
        content = MODEL if request.url.path.endswith(".onnx") else CONFIG
        return httpx.Response(200, content=content, request=request)

    runtime.voice_downloader = VoiceDownloader(
        runtime.voice_catalog,
        tmp_path / "installed",
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        validator=lambda *_: None,
    )
    runtime.voice_deleter = VoiceDeleter(
        runtime.voice_catalog, tmp_path / "installed", tmp_path / "custom"
    )
    runtime.voice_importer = VoiceImporter(tmp_path / "custom", validator=lambda *_: None)


def test_voice_management_endpoints_are_post_only(client, runtime, tmp_path) -> None:
    configure_voice_services(runtime, tmp_path)

    listed = client.post("/api/v1/getVoices", json={})
    downloaded = client.post(
        "/api/v1/downloadVoice", json={"voiceId": "en_US-ljspeech-medium"}
    )
    installed = client.post("/api/v1/getVoices", json={})
    get_attempt = client.get("/api/v1/getVoices")

    assert listed.status_code == 200
    listed_by_id = {voice["id"]: voice for voice in listed.json()["voices"]}
    assert listed_by_id["en_US-ljspeech-medium"]["status"] == "downloadRequired"
    assert downloaded.status_code == 200
    assert downloaded.json()["voice"]["status"] == "ready"
    downloaded_model_path = Path(downloaded.json()["voice"]["modelPath"])
    assert downloaded_model_path.is_absolute()
    installed_by_id = {voice["id"]: voice for voice in installed.json()["voices"]}
    assert Path(installed_by_id["en_US-ljspeech-medium"]["modelPath"]).is_absolute()
    assert get_attempt.status_code == 405


def test_delete_voice_removes_installed_files_and_updates_catalog(
    client, runtime, tmp_path
) -> None:
    configure_voice_services(runtime, tmp_path)
    client.post("/api/v1/downloadVoice", json={"voiceId": "en_US-ljspeech-medium"})

    deleted = client.post(
        "/api/v1/deleteVoice", json={"voiceId": "en_US-ljspeech-medium"}
    )
    listed = client.post("/api/v1/getVoices", json={})

    assert deleted.status_code == deleted.json()["reasonCode"] == 200
    assert deleted.json()["deletedVoiceId"] == "en_US-ljspeech-medium"
    assert not (tmp_path / "installed" / "en_US-ljspeech-medium").exists()
    listed_by_id = {voice["id"]: voice for voice in listed.json()["voices"]}
    assert listed_by_id["en_US-ljspeech-medium"]["status"] == "downloadRequired"


def test_delete_voice_rejects_voice_that_is_not_installed(client, runtime, tmp_path) -> None:
    configure_voice_services(runtime, tmp_path)

    response = client.post(
        "/api/v1/deleteVoice", json={"voiceId": "en_US-ljspeech-medium"}
    )

    assert response.status_code == response.json()["reasonCode"] == 404
    assert response.json()["reasonText"] == "Voice is not installed"


def test_import_voice_rejects_json_url_payload(client, runtime, tmp_path) -> None:
    configure_voice_services(runtime, tmp_path)

    response = client.post(
        "/api/v1/importVoice",
        json={
            "displayName": "Remote voice",
            "license": "CC0-1.0",
            "rightsConfirmed": True,
            "modelUrl": "https://voices.test/model.onnx",
            "configUrl": "https://voices.test/model.onnx.json",
        },
    )

    assert response.status_code == response.json()["reasonCode"] == 415
    assert response.json()["reasonText"] == "Only multipart local voice import is supported"


def test_import_voice_accepts_multipart_local_files(client, runtime, tmp_path) -> None:
    configure_voice_services(runtime, tmp_path)

    response = client.post(
        "/api/v1/importVoice",
        data={
            "displayName": "Local voice",
            "license": "CC0-1.0",
            "rightsConfirmed": "true",
        },
        files={
            "model": ("local.onnx", MODEL, "application/octet-stream"),
            "config": ("local.onnx.json", CONFIG, "application/json"),
        },
    )

    assert response.status_code == response.json()["reasonCode"] == 200
    assert response.json()["voice"]["id"] == "custom/local-voice"


def test_import_voice_media_type_is_exact_and_case_insensitive(
    client, runtime, tmp_path
) -> None:
    configure_voice_services(runtime, tmp_path)

    accepted = client.post(
        "/api/v1/importVoice",
        content=b"",
        headers={"Content-Type": "Multipart/Form-Data; boundary=empty"},
    )
    rejected = client.post(
        "/api/v1/importVoice",
        content=b"",
        headers={"Content-Type": "multipart/form-datax; boundary=empty"},
    )

    assert accepted.status_code == accepted.json()["reasonCode"] == 400
    assert rejected.status_code == rejected.json()["reasonCode"] == 415


def test_restricted_download_requires_license_confirmation(client, runtime, tmp_path) -> None:
    configure_voice_services(runtime, tmp_path)

    unconfirmed = client.post(
        "/api/v1/downloadVoice", json={"voiceId": "en_US-restricted-medium"}
    )
    confirmed = client.post(
        "/api/v1/downloadVoice",
        json={"voiceId": "en_US-restricted-medium", "licenseConfirmed": True},
    )

    assert unconfirmed.status_code == unconfirmed.json()["reasonCode"] == 403
    assert confirmed.status_code == confirmed.json()["reasonCode"] == 200


def test_incomplete_catalog_download_preserves_bad_gateway_contract(
    client, runtime, tmp_path
) -> None:
    configure_voice_services(runtime, tmp_path)

    response = client.post(
        "/api/v1/downloadVoice", json={"voiceId": "en_US-incomplete-medium"}
    )

    assert response.status_code == response.json()["reasonCode"] == 502
    assert "metadata" in response.json()["reasonText"].casefold()
