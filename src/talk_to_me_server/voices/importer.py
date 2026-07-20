from __future__ import annotations

import hashlib
import inspect
import re
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from talk_to_me_server.storage.atomic import atomic_write_json
from talk_to_me_server.voices.downloader import (
    VoiceConflict,
    _validate_config,
)
from talk_to_me_server.voices.models import VoiceDescriptor, VoiceStatus


class RightsConfirmationRequired(ValueError):
    pass


class VoiceImportError(ValueError):
    pass


class VoiceImporter:
    def __init__(
        self,
        custom_root: Path,
        validator: Callable[[Path, Path], Any],
    ) -> None:
        self.custom_root = custom_root
        self.validator = validator

    def import_local(
        self,
        model_path: Path,
        config_path: Path,
        *,
        display_name: str,
        license_name: str,
        rights_confirmed: bool,
    ) -> VoiceDescriptor:
        staging, destination, slug = self._prepare(
            display_name, rights_confirmed=rights_confirmed
        )
        try:
            shutil.copyfile(model_path, staging / "model.onnx")
            shutil.copyfile(config_path, staging / "model.onnx.json")
            self._validate_sync(staging)
            return self._activate(staging, destination, slug, display_name, license_name)
        finally:
            _remove_staging(staging)

    def import_bytes(
        self,
        model: bytes,
        config: bytes,
        *,
        display_name: str,
        license_name: str,
        rights_confirmed: bool,
    ) -> VoiceDescriptor:
        staging, destination, slug = self._prepare(
            display_name, rights_confirmed=rights_confirmed
        )
        try:
            (staging / "model.onnx").write_bytes(model)
            (staging / "model.onnx.json").write_bytes(config)
            self._validate_sync(staging)
            return self._activate(staging, destination, slug, display_name, license_name)
        finally:
            _remove_staging(staging)

    def _prepare(
        self, display_name: str, *, rights_confirmed: bool
    ) -> tuple[Path, Path, str]:
        if not rights_confirmed:
            raise RightsConfirmationRequired("Rights confirmation is required")
        slug = _slug(display_name)
        if not slug:
            raise VoiceImportError("Voice display name must contain letters or numbers")
        self.custom_root.mkdir(parents=True, exist_ok=True)
        destination = self.custom_root / slug
        if destination.exists():
            raise VoiceConflict("A custom voice with this name already exists")
        staging = self.custom_root / f".staging-{uuid4().hex}"
        staging.mkdir()
        return staging, destination, slug

    def _validate_sync(self, staging: Path) -> None:
        _validate_config(staging / "model.onnx.json")
        try:
            validation = self.validator(
                staging / "model.onnx", staging / "model.onnx.json"
            )
        except Exception as error:
            raise VoiceImportError("Piper rejected the custom voice") from error
        if inspect.isawaitable(validation):
            raise VoiceImportError("Asynchronous validators require remote import")

    @staticmethod
    def _activate(
        staging: Path,
        destination: Path,
        slug: str,
        display_name: str,
        license_name: str,
    ) -> VoiceDescriptor:
        model_path = staging / "model.onnx"
        config_path = staging / "model.onnx.json"
        voice_id = f"custom/{slug}"
        license_value = license_name.strip() or "User supplied"
        atomic_write_json(
            staging / "voice.json",
            {
                "id": voice_id,
                "name": display_name.strip(),
                "language": "und",
                "quality": "custom",
                "license": license_value,
                "source": "custom",
                "importedAt": datetime.now(UTC).isoformat(),
                "sizeBytes": model_path.stat().st_size,
                "modelSha256": _file_sha256(model_path),
                "configSha256": _file_sha256(config_path),
                "modelPath": str(destination / "model.onnx"),
                "configPath": str(destination / "model.onnx.json"),
            },
        )
        staging.rename(destination)
        return VoiceDescriptor(
            id=voice_id,
            name=display_name.strip(),
            language="und",
            quality="custom",
            size_bytes=(destination / "model.onnx").stat().st_size,
            license=license_value,
            source="custom",
            status=VoiceStatus.READY,
            model_path=destination / "model.onnx",
            config_path=destination / "model.onnx.json",
        )


def _slug(value: str) -> str:
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", value.casefold()))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_staging(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
