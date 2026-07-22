import json
from pathlib import Path

from talk_to_me_server.voices.catalog import VoiceCatalog
from talk_to_me_server.voices.licenses import VoiceLicensePolicy
from talk_to_me_server.voices.models import VoiceStatus


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_catalog_merges_official_installed_and_custom_with_provenance(tmp_path) -> None:
    official = tmp_path / "official.json"
    installed = tmp_path / "installed"
    custom = tmp_path / "custom"
    write_json(
        official,
        {
            "voices": [
                {
                    "id": "en_US-ljspeech-medium",
                    "name": "LJSpeech",
                    "language": "en-US",
                    "quality": "medium",
                    "sizeBytes": 63_000_000,
                    "license": "Public Domain",
                    "modelUrl": "https://example.test/model.onnx",
                    "configUrl": "https://example.test/model.onnx.json",
                },
                {
                    "id": "en_US-locked-medium",
                    "name": "Locked",
                    "language": "en-US",
                    "quality": "medium",
                    "sizeBytes": 1,
                    "license": "CC-BY-NC-4.0",
                    "modelUrl": "https://example.test/locked.onnx",
                    "configUrl": "https://example.test/locked.onnx.json",
                    "modelSha256": "a" * 64,
                    "configSha256": "b" * 64,
                },
                {
                    "id": "en_US-incomplete-medium",
                    "name": "Incomplete",
                    "language": "en-US",
                    "quality": "medium",
                    "license": "Public Domain",
                    "modelUrl": "https://example.test/incomplete.onnx",
                    "configUrl": "https://example.test/incomplete.onnx.json",
                    "modelSha256": "c" * 64,
                },
            ]
        },
    )
    write_json(
        installed / "en_US-ljspeech-medium" / "voice.json",
        {"id": "en_US-ljspeech-medium", "source": "official"},
    )
    write_json(
        custom / "acme" / "voice.json",
        {
            "id": "custom/acme",
            "name": "Acme",
            "language": "cs-CZ",
            "quality": "custom",
            "license": "User supplied",
            "source": "custom",
        },
    )
    policy = VoiceLicensePolicy.from_file(Path("master-data/voice-license-policy.json"))

    rows = {
        voice.id: voice
        for voice in VoiceCatalog(official, installed, custom, policy).list()
    }

    assert rows["en_US-ljspeech-medium"].source == "official"
    assert rows["en_US-ljspeech-medium"].status is VoiceStatus.READY
    locked = rows["en_US-locked-medium"]
    assert locked.status is VoiceStatus.DOWNLOAD_REQUIRED
    assert locked.downloadable is True
    assert locked.requires_license_confirmation is True
    assert (
        locked.license_notice
        == "Voice license is explicitly restricted by the redistribution policy."
    )
    assert locked.blocked_reason is None
    incomplete = rows["en_US-incomplete-medium"]
    assert incomplete.status is VoiceStatus.INVALID
    assert incomplete.downloadable is False
    assert incomplete.blocked_reason
    assert rows["custom/acme"].source == "custom"
    assert rows["custom/acme"].status is VoiceStatus.READY


def test_catalog_marks_malformed_installed_voice_invalid(tmp_path) -> None:
    official = tmp_path / "official.json"
    write_json(official, {"voices": []})
    broken = tmp_path / "installed" / "broken"
    write_json(broken / "voice.json", {"id": "broken", "source": "official"})
    policy = VoiceLicensePolicy.from_file(Path("master-data/voice-license-policy.json"))

    rows = VoiceCatalog(official, tmp_path / "installed", tmp_path / "custom", policy).list()

    assert rows[0].id == "broken"
    assert rows[0].status is VoiceStatus.INVALID


def test_catalog_resolves_manifest_paths_relative_to_voice_directory(tmp_path) -> None:
    official = tmp_path / "official.json"
    installed = tmp_path / "installed"
    voice_root = installed / "en_US-ljspeech-medium"
    write_json(
        official,
        {
            "voices": [
                {
                    "id": "en_US-ljspeech-medium",
                    "modelUrl": "https://example.test/model.onnx",
                    "configUrl": "https://example.test/model.onnx.json",
                    "modelSha256": "a" * 64,
                    "configSha256": "b" * 64,
                }
            ]
        },
    )
    (voice_root / "model.onnx").parent.mkdir(parents=True)
    (voice_root / "model.onnx").write_bytes(b"model")
    (voice_root / "model.onnx.json").write_text("{}", encoding="utf-8")
    write_json(
        voice_root / "voice.json",
        {
            "id": "en_US-ljspeech-medium",
            "modelPath": "model.onnx",
            "configPath": "model.onnx.json",
        },
    )
    policy = VoiceLicensePolicy.from_file(Path("master-data/voice-license-policy.json"))

    voice = VoiceCatalog(official, installed, tmp_path / "custom", policy).get(
        "en_US-ljspeech-medium"
    )

    assert voice is not None
    assert voice.model_path == voice_root / "model.onnx"
    assert voice.config_path == voice_root / "model.onnx.json"


def test_catalog_recovers_stale_absolute_manifest_paths_from_local_files(tmp_path) -> None:
    official = tmp_path / "official.json"
    installed = tmp_path / "installed"
    voice_root = installed / "en_US-ljspeech-medium"
    write_json(
        official,
        {
            "voices": [
                {
                    "id": "en_US-ljspeech-medium",
                    "modelUrl": "https://example.test/model.onnx",
                    "configUrl": "https://example.test/model.onnx.json",
                    "modelSha256": "a" * 64,
                    "configSha256": "b" * 64,
                }
            ]
        },
    )
    (voice_root / "model.onnx").parent.mkdir(parents=True)
    (voice_root / "model.onnx").write_bytes(b"model")
    (voice_root / "model.onnx.json").write_text("{}", encoding="utf-8")
    write_json(
        voice_root / "voice.json",
        {
            "id": "en_US-ljspeech-medium",
            "modelPath": "Z:/removed-worktree/model.onnx",
            "configPath": "Z:/removed-worktree/model.onnx.json",
        },
    )
    policy = VoiceLicensePolicy.from_file(Path("master-data/voice-license-policy.json"))

    voice = VoiceCatalog(official, installed, tmp_path / "custom", policy).get(
        "en_US-ljspeech-medium"
    )

    assert voice is not None
    assert voice.model_path == voice_root / "model.onnx"
    assert voice.config_path == voice_root / "model.onnx.json"
