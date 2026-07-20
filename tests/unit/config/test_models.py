from pathlib import Path

import pytest
from pydantic import ValidationError

from talk_to_me_server.config.models import Settings


MASTER = Path("master-data/setup.json")


def test_master_setup_is_valid_and_has_approved_defaults() -> None:
    raw = MASTER.read_text(encoding="utf-8")
    settings = Settings.model_validate_json(raw)

    assert settings.network.port == 44448
    assert settings.network.remote_management_enabled is True
    assert settings.voice.speaker == "en_US-ljspeech-medium"
    assert settings.general.workers == 4
    assert settings.limits.max_request_body_bytes == 67_108_864
    assert "severity" not in settings.voice.model_dump(mode="json")
    assert '"severity"' not in raw


def test_legacy_names_and_unknown_fields_are_rejected() -> None:
    raw = MASTER.read_text(encoding="utf-8").replace('"workers": 4', '"threads": 4')

    with pytest.raises(ValidationError):
        Settings.model_validate_json(raw)


def test_restart_field_diff_is_exact() -> None:
    current = Settings.model_validate_json(MASTER.read_text(encoding="utf-8"))
    changed = current.model_copy(
        update={"network": current.network.model_copy(update={"port": 5555})}
    )

    assert changed.restart_required_fields(current) == ("network.port",)
