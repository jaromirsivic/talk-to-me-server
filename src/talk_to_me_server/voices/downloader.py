from __future__ import annotations

import hashlib
import inspect
import json
import logging
import re
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from talk_to_me_server.storage.atomic import atomic_write_json
from talk_to_me_server.voices.catalog import VoiceCatalog
from talk_to_me_server.voices.models import VoiceDescriptor, VoiceStatus


MODEL_LIMIT = 2 * 1024 * 1024 * 1024
CONFIG_LIMIT = 4 * 1024 * 1024
SAFE_VOICE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
LOGGER = logging.getLogger("talk_to_me_server")


class VoiceDownloadError(RuntimeError):
    pass


class VoiceNotFound(VoiceDownloadError):
    pass


class LicenseRestricted(VoiceDownloadError):
    pass


class VoiceUnavailable(VoiceDownloadError):
    pass


class ChecksumMismatch(VoiceDownloadError):
    pass


class DownloadTooLarge(VoiceDownloadError):
    pass


class VoiceConflict(VoiceDownloadError):
    pass


class VoiceDownloader:
    def __init__(
        self,
        catalog: VoiceCatalog,
        installed_root: Path,
        http_client: httpx.AsyncClient,
        validator: Callable[[Path, Path], Any],
    ) -> None:
        self.catalog = catalog
        self.installed_root = installed_root
        self.http_client = http_client
        self.validator = validator

    async def download(
        self, voice_id: str, *, license_confirmed: bool = False
    ) -> VoiceDescriptor:
        LOGGER.info(
            "Voice download started",
            extra={"component": "voices", "event": "voice.download.started"},
        )
        if not SAFE_VOICE_ID.fullmatch(voice_id):
            raise VoiceNotFound("Voice does not exist")
        descriptor = self.catalog.get(voice_id)
        if descriptor is None or descriptor.source != "official":
            raise VoiceNotFound("Voice does not exist")
        if descriptor.status is VoiceStatus.READY:
            return descriptor
        if not descriptor.downloadable:
            raise VoiceUnavailable(
                descriptor.blocked_reason or "Voice catalog entry is unavailable"
            )
        if descriptor.requires_license_confirmation and not license_confirmed:
            raise LicenseRestricted(
                descriptor.license_notice or "Voice license confirmation is required"
            )
        if not (
            descriptor.model_url
            and descriptor.config_url
            and (descriptor.model_sha256 or descriptor.model_md5)
            and (descriptor.config_sha256 or descriptor.config_md5)
        ):
            raise VoiceUnavailable("Voice catalog entry is incomplete")

        self.installed_root.mkdir(parents=True, exist_ok=True)
        staging = self.installed_root / f".staging-{uuid4().hex}"
        destination = self.installed_root / voice_id
        if destination.exists():
            raise VoiceConflict("Voice destination already exists")
        staging.mkdir()
        model_path = staging / "model.onnx"
        config_path = staging / "model.onnx.json"
        try:
            model_sha256 = await self._download_file(
                descriptor.model_url,
                model_path,
                MODEL_LIMIT,
                descriptor.model_sha256,
                descriptor.model_md5,
            )
            config_sha256 = await self._download_file(
                descriptor.config_url,
                config_path,
                CONFIG_LIMIT,
                descriptor.config_sha256,
                descriptor.config_md5,
            )
            _validate_config(config_path)
            try:
                validation = self.validator(model_path, config_path)
                if inspect.isawaitable(validation):
                    await validation
            except Exception as error:
                raise VoiceDownloadError("Piper rejected the downloaded voice") from error
            atomic_write_json(
                staging / "voice.json",
                {
                    "id": descriptor.id,
                    "name": descriptor.name,
                    "language": descriptor.language,
                    "quality": descriptor.quality,
                    "license": descriptor.license,
                    "source": "official",
                    "modelUrl": descriptor.model_url,
                    "configUrl": descriptor.config_url,
                    "modelSha256": model_sha256,
                    "configSha256": config_sha256,
                    "modelMd5": descriptor.model_md5,
                    "configMd5": descriptor.config_md5,
                    "licenseDecision": (
                        "confirmed"
                        if descriptor.requires_license_confirmation
                        else "approved"
                    ),
                    "importedAt": datetime.now(UTC).isoformat(),
                    "modelPath": "model.onnx",
                    "configPath": "model.onnx.json",
                },
            )
            staging.rename(destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        activated = self.catalog.get(voice_id)
        if activated is None:
            raise VoiceDownloadError("Downloaded voice is missing from the catalog")
        LOGGER.info(
            "Voice download completed",
            extra={"component": "voices", "event": "voice.download.completed"},
        )
        return activated

    async def _download_file(
        self,
        url: str,
        destination: Path,
        limit: int,
        expected_sha256: str | None,
        expected_md5: str | None,
    ) -> str:
        return await download_to_file(
            self.http_client,
            url,
            destination,
            limit,
            expected_sha256=expected_sha256,
            expected_md5=expected_md5,
        )


async def download_to_file(
    http_client: httpx.AsyncClient,
    url: str,
    destination: Path,
    limit: int,
    *,
    expected_sha256: str | None = None,
    expected_md5: str | None = None,
) -> str:
    _validate_remote_url(url)
    digest = hashlib.sha256()
    md5_digest = hashlib.md5(usedforsecurity=False)
    total = 0
    try:
        async with http_client.stream("GET", url) as response:
            response.raise_for_status()
            _validate_remote_url(str(response.url))
            with destination.open("wb") as stream:
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > limit:
                        raise DownloadTooLarge(f"Downloaded file exceeds {limit} bytes")
                    digest.update(chunk)
                    md5_digest.update(chunk)
                    stream.write(chunk)
    except httpx.HTTPError as error:
        raise VoiceDownloadError("Voice download failed") from error
    actual = digest.hexdigest()
    if expected_sha256 is not None and actual.casefold() != expected_sha256.casefold():
        raise ChecksumMismatch("Downloaded file checksum does not match the catalog")
    if expected_md5 is not None and md5_digest.hexdigest().casefold() != expected_md5.casefold():
        raise ChecksumMismatch("Downloaded file checksum does not match the catalog")
    return actual


def _validate_remote_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise VoiceDownloadError("Voice URL must use HTTP or HTTPS")


def _validate_config(path: Path) -> None:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
        sample_rate = config["audio"]["sample_rate"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise VoiceDownloadError("Piper voice configuration is invalid") from error
    if not isinstance(sample_rate, int) or sample_rate <= 0:
        raise VoiceDownloadError("Piper voice sample rate is invalid")
