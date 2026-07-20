from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from talk_to_me_server.tts.piper_engine import validate_wav


class WorkerEngine(Protocol):
    def synthesize(self, text: str, output: Path) -> None: ...


EngineFactory = Callable[[Path, Path], WorkerEngine]


@dataclass(frozen=True)
class WorkerCommand:
    job_id: str
    index: int
    text: str
    model_path: Path
    config_path: Path
    output_path: Path


@dataclass(frozen=True)
class WorkerResult:
    job_id: str
    index: int
    output_path: Path
    process_id: int
    worker_index: int


_engine_factory: EngineFactory | None = None
_engines: dict[tuple[Path, Path], WorkerEngine] = {}
_worker_index = 0


def initialize_worker(engine_factory: EngineFactory, worker_counter: Any) -> None:
    global _engine_factory, _worker_index
    _engine_factory = engine_factory
    with worker_counter.get_lock():
        _worker_index = worker_counter.value
        worker_counter.value += 1
    _engines.clear()


def execute_worker(command: WorkerCommand) -> WorkerResult:
    if _engine_factory is None:
        raise RuntimeError("worker engine factory is not initialized")
    key = (command.model_path.resolve(), command.config_path.resolve())
    engine = _engines.get(key)
    if engine is None:
        engine = _engine_factory(*key)
        _engines[key] = engine
    engine.synthesize(command.text, command.output_path)
    validate_wav(command.output_path)
    return WorkerResult(
        job_id=command.job_id,
        index=command.index,
        output_path=command.output_path,
        process_id=os.getpid(),
        worker_index=_worker_index,
    )
