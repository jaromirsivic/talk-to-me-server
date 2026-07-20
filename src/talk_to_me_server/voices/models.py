from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from talk_to_me_server.config.models import StrictModel


class VoiceStatus(StrEnum):
    READY = "ready"
    DOWNLOAD_REQUIRED = "downloadRequired"
    DOWNLOADING = "downloading"
    INVALID = "invalid"


class VoiceDescriptor(StrictModel):
    id: str
    name: str
    language: str
    quality: str
    size_bytes: int | None = None
    license: str | None = None
    source: Literal["official", "custom"]
    status: VoiceStatus
    downloadable: bool = False
    blocked_reason: str | None = None
    requires_license_confirmation: bool = False
    license_notice: str | None = None
    model_url: str | None = None
    config_url: str | None = None
    model_sha256: str | None = None
    config_sha256: str | None = None
    model_md5: str | None = None
    config_md5: str | None = None
    model_path: Path | None = None
    config_path: Path | None = None
