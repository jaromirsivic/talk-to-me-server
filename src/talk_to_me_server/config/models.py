from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class StrictModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        populate_by_name=True,
        validate_assignment=True,
    )


class Device(StrEnum):
    CPU = "CPU"


class Theme(StrEnum):
    LIGHT = "light"
    DARK = "dark"


class NetworkSettings(StrictModel):
    ipv4_address: str = "127.0.0.1"
    ipv4_enabled: bool = True
    ipv6_address: str = "::1"
    ipv6_enabled: bool = True
    port: int = Field(default=44448, ge=1, le=65_535)
    remote_management_enabled: bool = True

    @model_validator(mode="after")
    def require_listener(self) -> NetworkSettings:
        if not self.ipv4_enabled and not self.ipv6_enabled:
            raise ValueError("at least one network family must be enabled")
        return self


class VoiceSettings(StrictModel):
    tts: Literal["Piper"] = "Piper"
    speaker: str = "en_US-ljspeech-medium"
    volume: int = Field(default=100, ge=0, le=100)


class DirectorySettings(StrictModel):
    temp_directory: Path = Path("./data/temp")
    speech_directory: Path = Path("./data/speech")
    text_directory: Path = Path("./data/text")
    garbage_collector_timeout: int = Field(default=1_000_000_000, ge=0)


class GeneralSettings(StrictModel):
    device: Device = Device.CPU
    workers: int = Field(default=4, ge=1, le=16)
    directories: DirectorySettings = Field(default_factory=DirectorySettings)
    theme: Theme = Theme.LIGHT


class LimitSettings(StrictModel):
    max_queued_jobs: int = Field(default=100, ge=1, le=100)
    max_request_body_bytes: int = Field(default=67_108_864, ge=1, le=67_108_864)


class Settings(StrictModel):
    version: Literal[1] = 1
    network: NetworkSettings
    voice: VoiceSettings
    general: GeneralSettings
    limits: LimitSettings

    def restart_required_fields(self, other: Settings) -> tuple[str, ...]:
        candidates = (
            (
                "network.ipv4Address",
                self.network.ipv4_address,
                other.network.ipv4_address,
            ),
            (
                "network.ipv4Enabled",
                self.network.ipv4_enabled,
                other.network.ipv4_enabled,
            ),
            (
                "network.ipv6Address",
                self.network.ipv6_address,
                other.network.ipv6_address,
            ),
            (
                "network.ipv6Enabled",
                self.network.ipv6_enabled,
                other.network.ipv6_enabled,
            ),
            ("network.port", self.network.port, other.network.port),
            (
                "network.remoteManagementEnabled",
                self.network.remote_management_enabled,
                other.network.remote_management_enabled,
            ),
            ("general.workers", self.general.workers, other.general.workers),
            ("general.device", self.general.device, other.general.device),
            (
                "general.directories",
                self.general.directories,
                other.general.directories,
            ),
            (
                "limits.maxQueuedJobs",
                self.limits.max_queued_jobs,
                other.limits.max_queued_jobs,
            ),
            (
                "limits.maxRequestBodyBytes",
                self.limits.max_request_body_bytes,
                other.limits.max_request_body_bytes,
            ),
        )
        return tuple(name for name, current, previous in candidates if current != previous)
