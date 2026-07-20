from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class SynthesisCommand:
    job_id: str
    index: int
    text: str
    speaker: str
    output_path: Path


@dataclass(frozen=True)
class SynthesisResult:
    job_id: str
    index: int
    output_path: Path
    process_id: int
    worker_index: int = 0


class SynthesisPool(Protocol):
    async def synthesize(self, command: SynthesisCommand) -> SynthesisResult: ...
