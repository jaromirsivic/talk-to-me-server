from __future__ import annotations

import re
import shutil
from pathlib import Path

from talk_to_me_server.voices.catalog import VoiceCatalog
from talk_to_me_server.voices.models import VoiceStatus


SAFE_VOICE_PART = re.compile(r"^[A-Za-z0-9_.-]+$")


class VoiceDeleteError(RuntimeError):
    pass


class VoiceNotInstalled(VoiceDeleteError):
    pass


class VoiceDeleter:
    def __init__(
        self, catalog: VoiceCatalog, installed_root: Path, custom_root: Path
    ) -> None:
        self.catalog = catalog
        self.installed_root = installed_root
        self.custom_root = custom_root

    def delete(self, voice_id: str) -> None:
        voice = self.catalog.get(voice_id)
        if voice is None or voice.status is not VoiceStatus.READY:
            raise VoiceNotInstalled("Voice is not installed")

        destination = self._destination(voice_id, voice.source)
        if not destination.is_dir():
            raise VoiceNotInstalled("Voice is not installed")
        shutil.rmtree(destination)

    def _destination(self, voice_id: str, source: str) -> Path:
        if source == "official" and SAFE_VOICE_PART.fullmatch(voice_id):
            return self.installed_root / voice_id
        prefix, separator, name = voice_id.partition("/")
        if (
            source == "custom"
            and prefix == "custom"
            and separator
            and SAFE_VOICE_PART.fullmatch(name)
        ):
            return self.custom_root / name
        raise VoiceNotInstalled("Voice is not installed")
