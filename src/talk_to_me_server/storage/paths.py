from __future__ import annotations

from pathlib import Path


class PathEscapeError(ValueError):
    pass


def contained_path(root: Path, *parts: str) -> Path:
    canonical_root = root.resolve(strict=True)
    for part in parts:
        parsed = Path(part)
        if not part or parsed.is_absolute() or len(parsed.parts) != 1 or part in {".", ".."}:
            raise PathEscapeError(f"invalid contained path component: {part!r}")
    candidate = canonical_root.joinpath(*parts).resolve(strict=False)
    if not candidate.is_relative_to(canonical_root):
        raise PathEscapeError(f"path escapes storage root: {candidate}")
    return candidate
