from __future__ import annotations

from enum import StrEnum
import math

from pydantic import Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from talk_to_me_server.config.models import StrictModel


class Importance(StrEnum):
    HIGH = "high"
    LOW = "low"


class QueueInfoMode(StrEnum):
    MIN = "min"
    MAX = "max"


class QueueInfoRequest(StrictModel):
    mode: QueueInfoMode = QueueInfoMode.MAX


class TextToSpeechRequest(StrictModel):
    value: str | None = Field(default=None, exclude=True)
    values: list[str] | None = None
    importance: Importance = Importance.HIGH
    volume_multiplier: float = 1.0
    calculate_stats: bool = False
    wait_until_playback_finished: bool = False

    @model_validator(mode="before")
    @classmethod
    def require_exactly_one_text_shape(cls, data):
        if not isinstance(data, dict):
            return data
        has_value = "value" in data
        has_values = "values" in data
        if has_value == has_values:
            raise ValueError("exactly one of value or values is required")
        if has_value and data.get("value") is None:
            raise ValueError("value must be a string")
        return data

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str | None) -> str | None:
        if value is not None and len(value) > 255 * 16_384:
            raise PydanticCustomError(
                "text_limit_exceeded",
                "value contains more than 4177920 Unicode code points",
            )
        return value

    @field_validator("values")
    @classmethod
    def validate_values(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        if len(values) > 255:
            raise PydanticCustomError(
                "text_limit_exceeded", "values contains more than 255 items"
            )
        if any(len(value) > 16_384 for value in values):
            raise PydanticCustomError(
                "text_limit_exceeded",
                "a value contains more than 16384 Unicode code points",
            )
        return values

    @field_validator("volume_multiplier")
    @classmethod
    def clamp_volume_multiplier(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("volumeMultiplier must be a finite number")
        return min(1.0, max(0.0, value))

    def with_values(self, values: list[str]) -> TextToSpeechRequest:
        return TextToSpeechRequest(
            values=values,
            importance=self.importance,
            volume_multiplier=self.volume_multiplier,
            calculate_stats=self.calculate_stats,
            wait_until_playback_finished=self.wait_until_playback_finished,
        )
