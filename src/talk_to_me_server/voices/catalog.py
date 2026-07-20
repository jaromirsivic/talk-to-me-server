from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from talk_to_me_server.voices.licenses import VoiceLicensePolicy
from talk_to_me_server.voices.models import VoiceDescriptor, VoiceStatus


class VoiceCatalog:
    def __init__(
        self,
        official_cache: Path,
        installed_root: Path,
        custom_root: Path,
        policy: VoiceLicensePolicy,
    ) -> None:
        self.official_cache = official_cache
        self.installed_root = installed_root
        self.custom_root = custom_root
        self.policy = policy

    def list(self) -> tuple[VoiceDescriptor, ...]:
        records = self._official_records()
        installed = self._manifests(self.installed_root)
        custom = self._manifests(self.custom_root)
        voices: dict[str, VoiceDescriptor] = {}
        for record in records:
            voice_id = str(record["id"])
            decision = self.policy.classify(record.get("license"))
            is_installed = voice_id in installed
            complete = self._is_complete(record)
            status = (
                VoiceStatus.READY
                if is_installed
                else VoiceStatus.DOWNLOAD_REQUIRED
                if complete
                else VoiceStatus.INVALID
            )
            voices[voice_id] = VoiceDescriptor(
                id=voice_id,
                name=str(record.get("name") or voice_id),
                language=str(record.get("language") or "und"),
                quality=str(record.get("quality") or "unknown"),
                size_bytes=record.get("sizeBytes"),
                license=record.get("license"),
                source="official",
                status=status,
                downloadable=complete and not is_installed,
                blocked_reason=None if is_installed or complete else "Voice metadata is incomplete.",
                requires_license_confirmation=decision.requires_confirmation,
                license_notice=decision.notice,
                model_url=record.get("modelUrl"),
                config_url=record.get("configUrl"),
                model_sha256=record.get("modelSha256"),
                config_sha256=record.get("configSha256"),
                model_md5=record.get("modelMd5"),
                config_md5=record.get("configMd5"),
                model_path=self._manifest_path(installed.get(voice_id), "modelPath"),
                config_path=self._manifest_path(installed.get(voice_id), "configPath"),
            )
        for voice_id, manifest in custom.items():
            voices[voice_id] = self._custom_descriptor(voice_id, manifest)
        for voice_id in installed.keys() - voices.keys():
            voices[voice_id] = VoiceDescriptor(
                id=voice_id,
                name=str(installed[voice_id].get("name") or voice_id),
                language=str(installed[voice_id].get("language") or "und"),
                quality=str(installed[voice_id].get("quality") or "unknown"),
                license=installed[voice_id].get("license"),
                source="official",
                status=VoiceStatus.INVALID,
                blocked_reason="Installed voice is absent from the official catalog.",
            )
        return tuple(
            sorted(
                voices.values(),
                key=lambda voice: (voice.language.casefold(), voice.name.casefold(), voice.quality),
            )
        )

    def get(self, voice_id: str) -> VoiceDescriptor | None:
        return next((voice for voice in self.list() if voice.id == voice_id), None)

    def _official_records(self) -> list[dict[str, Any]]:
        data = json.loads(self.official_cache.read_text(encoding="utf-8"))
        records = data.get("voices")
        if not isinstance(records, list):
            raise ValueError("official catalog cache must contain a voices array")
        return records

    @staticmethod
    def _is_complete(record: dict[str, Any]) -> bool:
        return bool(
            record.get("modelUrl")
            and record.get("configUrl")
            and (record.get("modelSha256") or record.get("modelMd5"))
            and (record.get("configSha256") or record.get("configMd5"))
        )

    @staticmethod
    def _manifests(root: Path) -> dict[str, dict[str, Any]]:
        if not root.exists():
            return {}
        result: dict[str, dict[str, Any]] = {}
        for path in root.glob("*/voice.json"):
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            voice_id = manifest.get("id")
            if isinstance(voice_id, str) and voice_id:
                result[voice_id] = manifest
        return result

    @staticmethod
    def _custom_descriptor(voice_id: str, manifest: dict[str, Any]) -> VoiceDescriptor:
        return VoiceDescriptor(
            id=voice_id,
            name=str(manifest.get("name") or voice_id),
            language=str(manifest.get("language") or "und"),
            quality=str(manifest.get("quality") or "custom"),
            size_bytes=manifest.get("sizeBytes"),
            license=manifest.get("license"),
            source="custom",
            status=VoiceStatus.READY,
            model_path=manifest.get("modelPath"),
            config_path=manifest.get("configPath"),
        )

    @staticmethod
    def _manifest_path(manifest: dict[str, Any] | None, key: str) -> Path | None:
        if manifest is None:
            return None
        value = manifest.get(key)
        return Path(value) if isinstance(value, str) else None
