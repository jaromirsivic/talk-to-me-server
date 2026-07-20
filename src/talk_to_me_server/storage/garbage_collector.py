from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from talk_to_me_server.storage.paths import contained_path


JOB_ID_PATTERN = re.compile(r"^\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}_\d+$")
TERMINAL_STATES = {"finished", "failed"}
LOGGER = logging.getLogger("talk_to_me_server")


@dataclass(frozen=True)
class CollectionReport:
    deleted: tuple[str, ...]
    skipped_active: tuple[str, ...]
    failures: tuple[tuple[str, str], ...]


class GarbageCollector:
    def __init__(
        self,
        root: Path,
        timeout_seconds: int,
        *,
        active_ids: Callable[[], set[str]] | None = None,
        interval_seconds: float = 60,
    ) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self._root = root.resolve(strict=True)
        self._timeout_seconds = timeout_seconds
        self._active_ids = active_ids or set
        self._interval_seconds = interval_seconds

    async def run(self) -> None:
        while True:
            report = await asyncio.to_thread(
                self.collect,
                now=datetime.now().astimezone(),
                active_ids=self._active_ids(),
            )
            LOGGER.info(
                "Garbage collection completed",
                extra={
                    "component": "storage",
                    "event": "garbage_collection.completed",
                },
            )
            if report.failures:
                LOGGER.warning(
                    "Garbage collection completed with failures",
                    extra={
                        "component": "storage",
                        "event": "garbage_collection.failed",
                    },
                )
            await asyncio.sleep(self._interval_seconds)

    def collect(self, *, now: datetime, active_ids: set[str]) -> CollectionReport:
        if now.utcoffset() is None:
            raise ValueError("garbage collection time must be timezone-aware")
        deleted: list[str] = []
        skipped_active: list[str] = []
        failures: list[tuple[str, str]] = []
        for entry in self._root.iterdir():
            job_id = entry.name
            if not JOB_ID_PATTERN.fullmatch(job_id) or entry.is_symlink() or not entry.is_dir():
                continue
            if job_id in active_ids:
                skipped_active.append(job_id)
                continue
            try:
                canonical = contained_path(self._root, job_id)
                age = now.timestamp() - canonical.stat().st_mtime
                if age < self._timeout_seconds or not self._is_terminal(canonical):
                    continue
                shutil.rmtree(canonical)
                deleted.append(job_id)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                failures.append((job_id, str(error)))
        return CollectionReport(tuple(deleted), tuple(skipped_active), tuple(failures))

    @staticmethod
    def _is_terminal(job_directory: Path) -> bool:
        state_path = contained_path(job_directory, "job.json")
        state = json.loads(state_path.read_text(encoding="utf-8")).get("state")
        return state in TERMINAL_STATES
