from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LicenseDecision:
    freely_redistributable: bool
    normalized_license: str | None
    notice: str | None = None

    @property
    def requires_confirmation(self) -> bool:
        return not self.freely_redistributable


class VoiceLicensePolicy:
    def __init__(
        self,
        allowed: set[str],
        denied: set[str],
        aliases: dict[str, str],
        unknown_reason: str,
        restricted_reason: str,
    ) -> None:
        self._allowed = allowed
        self._denied = denied
        self._aliases = aliases
        self._unknown_reason = unknown_reason
        self._restricted_reason = restricted_reason

    @classmethod
    def from_file(cls, path: Path) -> VoiceLicensePolicy:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != 1:
            raise ValueError("unsupported voice license policy version")
        aliases = {
            cls._normalize(key): cls._normalize(value)
            for key, value in data.get("aliases", {}).items()
        }
        return cls(
            allowed={cls._normalize(value) for value in data["allow"]},
            denied={cls._normalize(value) for value in data["deny"]},
            aliases=aliases,
            unknown_reason=data["unknownReason"],
            restricted_reason=data["restrictedReason"],
        )

    def classify(self, license_id: str | None) -> LicenseDecision:
        if not license_id or not license_id.strip():
            return LicenseDecision(False, None, self._unknown_reason)
        normalized = self._normalize(license_id)
        normalized = self._aliases.get(normalized, normalized)
        if normalized in self._allowed:
            return LicenseDecision(True, normalized)
        if normalized in self._denied:
            return LicenseDecision(False, normalized, self._restricted_reason)
        return LicenseDecision(False, normalized, self._unknown_reason)

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.strip().upper().split())
