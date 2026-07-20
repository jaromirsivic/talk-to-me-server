import json
from pathlib import Path

import pytest

from talk_to_me_server.voices.importer import RightsConfirmationRequired, VoiceImporter


MODEL = b"custom-model"
CONFIG = json.dumps({"audio": {"sample_rate": 22_050}}).encode()


def test_local_import_copies_source_and_activates_custom_voice(tmp_path: Path) -> None:
    source_model = tmp_path / "source.onnx"
    source_config = tmp_path / "source.onnx.json"
    source_model.write_bytes(MODEL)
    source_config.write_bytes(CONFIG)
    importer = VoiceImporter(tmp_path / "custom", validator=lambda *_: None)

    voice = importer.import_local(
        source_model,
        source_config,
        display_name="My Czech Voice",
        license_name="CC0-1.0",
        rights_confirmed=True,
    )

    destination = tmp_path / "custom" / "my-czech-voice"
    assert voice.id == "custom/my-czech-voice"
    assert source_model.read_bytes() == MODEL
    assert (destination / "model.onnx").read_bytes() == MODEL
    assert json.loads((destination / "voice.json").read_text(encoding="utf-8"))["license"] == "CC0-1.0"
    assert not list((tmp_path / "custom").glob(".staging-*"))


def test_import_requires_explicit_rights_confirmation(tmp_path: Path) -> None:
    importer = VoiceImporter(tmp_path / "custom", validator=lambda *_: None)

    with pytest.raises(RightsConfirmationRequired):
        importer.import_bytes(
            MODEL,
            CONFIG,
            display_name="Unconfirmed Voice",
            license_name="Custom",
            rights_confirmed=False,
        )

    assert not (tmp_path / "custom").exists()


def test_importer_exposes_only_local_import_paths() -> None:
    assert hasattr(VoiceImporter, "import_bytes")
    assert not hasattr(VoiceImporter, "import_urls")
