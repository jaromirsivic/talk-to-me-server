from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from talk_to_me_server.config.models import Settings
from talk_to_me_server.storage.atomic import atomic_write_json


@dataclass(frozen=True)
class SaveResult:
    settings: Settings
    restart_fields: tuple[str, ...]


class SettingsService:
    def __init__(self, path: Path, defaults: Settings) -> None:
        self._path = path
        self._defaults = defaults.model_copy(deep=True)
        self._current: Settings | None = None
        self._lock = RLock()

    def initialize(self) -> Settings:
        with self._lock:
            if self._path.exists():
                loaded = load_settings(self._path, migrate_legacy_severity=True)
            else:
                loaded = self._defaults.model_copy(deep=True)
                atomic_write_json(self._path, loaded)
            self._current = loaded
            return loaded.model_copy(deep=True)

    def current(self) -> Settings:
        with self._lock:
            if self._current is None:
                raise RuntimeError("settings service has not been initialized")
            return self._current.model_copy(deep=True)

    def save(self, candidate: Settings) -> SaveResult:
        with self._lock:
            if self._current is None:
                raise RuntimeError("settings service has not been initialized")
            persisted = Settings.model_validate(candidate.model_dump(mode="json"))
            restart_fields = persisted.restart_required_fields(self._current)
            atomic_write_json(self._path, persisted)
            self._current = persisted
            return SaveResult(persisted.model_copy(deep=True), restart_fields)


def load_settings(path: Path, *, migrate_legacy_severity: bool = False) -> Settings:
    raw = json.loads(path.read_text(encoding="utf-8"))
    voice = raw.get("voice") if isinstance(raw, dict) else None
    migrated = False
    if migrate_legacy_severity and isinstance(voice, dict) and "severity" in voice:
        del voice["severity"]
        migrated = True
    settings = Settings.model_validate(raw)
    if migrate_legacy_severity and isinstance(voice, dict):
        migrated = migrated or voice.get("language") != settings.voice.language
    if migrated:
        atomic_write_json(path, settings)
    return settings
