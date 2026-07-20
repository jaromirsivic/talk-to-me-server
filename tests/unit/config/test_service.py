import json
from pathlib import Path

import pytest

from talk_to_me_server.config.models import Settings
from talk_to_me_server.config.service import SettingsService


MASTER = Path("master-data/setup.json")


@pytest.fixture
def approved_settings() -> Settings:
    return Settings.model_validate_json(MASTER.read_text(encoding="utf-8"))


def test_save_failure_keeps_memory_and_disk(monkeypatch, tmp_path, approved_settings) -> None:
    path = tmp_path / "setup.json"
    service = SettingsService(path, approved_settings)
    service.initialize()
    before = service.current()
    candidate = before.model_copy(
        update={"voice": before.voice.model_copy(update={"volume": 72})}
    )

    def fail_write(*_args, **_kwargs) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("talk_to_me_server.config.service.atomic_write_json", fail_write)

    with pytest.raises(OSError, match="disk full"):
        service.save(candidate)

    assert service.current() == before
    assert Settings.model_validate_json(path.read_text(encoding="utf-8")) == before


def test_save_returns_restart_fields_after_atomic_write(tmp_path, approved_settings) -> None:
    service = SettingsService(tmp_path / "setup.json", approved_settings)
    service.initialize()
    candidate = approved_settings.model_copy(
        update={
            "network": approved_settings.network.model_copy(update={"port": 5555}),
            "voice": approved_settings.voice.model_copy(update={"volume": 72}),
        }
    )

    result = service.save(candidate)

    assert result.settings == candidate
    assert result.restart_fields == ("network.port",)
    assert service.current().voice.volume == 72


def test_initialize_loads_existing_valid_settings(tmp_path, approved_settings) -> None:
    path = tmp_path / "setup.json"
    existing = approved_settings.model_copy(
        update={"voice": approved_settings.voice.model_copy(update={"volume": 41})}
    )
    path.write_text(existing.model_dump_json(by_alias=True), encoding="utf-8")

    service = SettingsService(path, approved_settings)
    service.initialize()

    assert service.current().voice.volume == 41


def test_initialize_preserves_existing_remote_management_false(
    tmp_path, approved_settings
) -> None:
    path = tmp_path / "setup.json"
    existing = approved_settings.model_copy(
        update={
            "network": approved_settings.network.model_copy(
                update={"remote_management_enabled": False}
            )
        }
    )
    path.write_text(existing.model_dump_json(by_alias=True), encoding="utf-8")
    service = SettingsService(path, approved_settings)

    service.initialize()

    assert service.current().network.remote_management_enabled is False


def test_initialize_removes_legacy_voice_severity_from_existing_setup(
    tmp_path, approved_settings
) -> None:
    path = tmp_path / "setup.json"
    existing = approved_settings.model_dump(mode="json", by_alias=True)
    existing["voice"]["severity"] = {
        "info": "acceptPlusGong",
        "debug": "accept",
        "warning": "acceptPlusGong",
        "error": "acceptPlusGong",
    }
    path.write_text(json.dumps(existing), encoding="utf-8")

    service = SettingsService(path, approved_settings)
    service.initialize()

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert "severity" not in persisted["voice"]
    assert service.current().voice == approved_settings.voice


def test_initialize_adds_derived_language_to_existing_setup(
    tmp_path, approved_settings
) -> None:
    path = tmp_path / "setup.json"
    existing = approved_settings.model_dump(mode="json", by_alias=True)
    del existing["voice"]["language"]
    path.write_text(json.dumps(existing), encoding="utf-8")

    service = SettingsService(path, approved_settings)
    service.initialize()

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["voice"]["language"] == "en_US"


def test_save_rederives_language_from_speaker(tmp_path, approved_settings) -> None:
    path = tmp_path / "setup.json"
    service = SettingsService(path, approved_settings)
    service.initialize()
    candidate = approved_settings.model_copy(deep=True)
    object.__setattr__(candidate.voice, "speaker", "cs_CZ-jirka-medium")
    object.__setattr__(candidate.voice, "language", "de_DE")

    result = service.save(candidate)

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert result.settings.voice.language == "cs_CZ"
    assert persisted["voice"]["language"] == "cs_CZ"
