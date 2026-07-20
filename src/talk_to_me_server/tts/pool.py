from __future__ import annotations

import asyncio
import logging
import multiprocessing
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from talk_to_me_server.tts.base import SynthesisCommand, SynthesisResult
from talk_to_me_server.tts.piper_engine import load_piper_engine
from talk_to_me_server.tts.worker import (
    EngineFactory,
    WorkerCommand,
    execute_worker,
    initialize_worker,
)


VoiceResolver = Callable[[str], tuple[Path, Path]]
LOGGER = logging.getLogger("talk_to_me_server")


class ProcessSynthesisPool:
    def __init__(
        self,
        workers: int,
        voice_resolver: VoiceResolver,
        *,
        engine_factory: EngineFactory = load_piper_engine,
        command_timeout: float = 300,
    ) -> None:
        if not 1 <= workers <= 16:
            raise ValueError("workers must be between 1 and 16")
        self.workers = workers
        self.voice_resolver = voice_resolver
        self.engine_factory = engine_factory
        self.command_timeout = command_timeout
        self._executor: ProcessPoolExecutor | None = None
        self._restart_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._executor is None:
            self._executor = self._new_executor()
            LOGGER.info(
                "Synthesis workers started",
                extra={"component": "synthesis", "event": "worker.started"},
            )

    async def synthesize(self, command: SynthesisCommand) -> SynthesisResult:
        if self._executor is None:
            raise RuntimeError("synthesis pool has not been started")
        model_path, config_path = self.voice_resolver(command.speaker)
        worker_command = WorkerCommand(
            job_id=command.job_id,
            index=command.index,
            text=command.text,
            model_path=model_path,
            config_path=config_path,
            output_path=command.output_path,
        )
        try:
            result = await self._submit(worker_command)
        except (BrokenProcessPool, TimeoutError):
            await self._restart()
            result = await self._submit(worker_command)
        return SynthesisResult(
            job_id=result.job_id,
            index=result.index,
            output_path=result.output_path,
            process_id=result.process_id,
            worker_index=result.worker_index,
        )

    async def _submit(self, command: WorkerCommand):
        executor = self._executor
        if executor is None:
            raise RuntimeError("synthesis pool is closed")
        future = asyncio.get_running_loop().run_in_executor(
            executor, execute_worker, command
        )
        return await asyncio.wait_for(future, timeout=self.command_timeout)

    async def _restart(self) -> None:
        async with self._restart_lock:
            previous = self._executor
            self._executor = self._new_executor()
            if previous is not None:
                previous.shutdown(wait=False, cancel_futures=True)
            LOGGER.warning(
                "Synthesis worker pool restarted",
                extra={"component": "synthesis", "event": "worker.restarted"},
            )

    def _new_executor(self) -> ProcessPoolExecutor:
        context = multiprocessing.get_context("spawn")
        worker_counter = context.Value("i", 0)
        return ProcessPoolExecutor(
            max_workers=self.workers,
            mp_context=context,
            initializer=initialize_worker,
            initargs=(self.engine_factory, worker_counter),
        )

    async def close(self) -> None:
        executor = self._executor
        self._executor = None
        if executor is not None:
            await asyncio.to_thread(
                executor.shutdown, wait=True, cancel_futures=True
            )
            LOGGER.info(
                "Synthesis workers stopped",
                extra={"component": "synthesis", "event": "worker.stopped"},
            )
