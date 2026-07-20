import json
from pathlib import Path

import pytest

from talk_to_me_server.voices.catalog import VoiceCatalog
from talk_to_me_server.voices.deleter import VoiceDeleter, VoiceNotInstalled
from talk_to_me_server.voices.licenses import VoiceLicensePolicy
from talk_to_me_server.voices.models import VoiceStatus


def build_catalog(tmp_path: Path) -> VoiceCatalog:
    official = tmp_path / "official.json"
    official.write_text(
        json.dumps(
            {
                "voices": [
                    {
                        "id": "en_US-amy-medium",
                        "name": "Amy",
                        "language": "en-US",
                        "quality": "medium",
                        "modelUrl": "https://voices.test/amy.onnx",
                        "configUrl": "https://voices.test/amy.onnx.json",
                        "modelSha256": "a" * 64,
                        "configSha256": "b" * 64,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return VoiceCatalog(
        official,
        tmp_path / "installed",
        tmp_path / "custom",
        VoiceLicensePolicy.from_file(Path("master-data/voice-license-policy.json")),
    )


def write_installed_voice(root: Path, directory_name: str, voice_id: str) -> Path:
    directory = root / directory_name
    directory.mkdir(parents=True)
    (directory / "model.onnx").write_bytes(b"model")
    (directory / "model.onnx.json").write_text("{}", encoding="utf-8")
    (directory / "voice.json").write_text(
        json.dumps(
            {
                "id": voice_id,
                "name": "Amy",
                "modelPath": str(directory / "model.onnx"),
                "configPath": str(directory / "model.onnx.json"),
            }
        ),
        encoding="utf-8",
    )
    return directory


def test_delete_official_voice_removes_files_and_restores_download_state(tmp_path) -> None:
    catalog = build_catalog(tmp_path)
    directory = write_installed_voice(
        catalog.installed_root, "en_US-amy-medium", "en_US-amy-medium"
    )
    deleter = VoiceDeleter(catalog, catalog.installed_root, catalog.custom_root)

    deleter.delete("en_US-amy-medium")

    assert not directory.exists()
    assert catalog.get("en_US-amy-medium").status is VoiceStatus.DOWNLOAD_REQUIRED


def test_delete_custom_voice_removes_it_from_catalog(tmp_path) -> None:
    catalog = build_catalog(tmp_path)
    directory = write_installed_voice(
        catalog.custom_root, "my-voice", "custom/my-voice"
    )
    deleter = VoiceDeleter(catalog, catalog.installed_root, catalog.custom_root)

    deleter.delete("custom/my-voice")

    assert not directory.exists()
    assert catalog.get("custom/my-voice") is None


def test_delete_rejects_voice_that_is_not_installed(tmp_path) -> None:
    catalog = build_catalog(tmp_path)
    deleter = VoiceDeleter(catalog, catalog.installed_root, catalog.custom_root)

    with pytest.raises(VoiceNotInstalled, match="not installed"):
        deleter.delete("en_US-amy-medium")
