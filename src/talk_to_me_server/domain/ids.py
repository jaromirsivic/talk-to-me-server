from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Lock


class JobIdGenerator:
    def __init__(self, archive_root: Path, sequence_start: int = 0) -> None:
        self._archive_root = archive_root
        self._sequence = sequence_start
        self._lock = Lock()

    def next_id(self, now: datetime) -> str:
        if now.utcoffset() is None:
            raise ValueError("job ID time must be timezone-aware")
        self._archive_root.mkdir(parents=True, exist_ok=True)
        prefix = now.strftime("%Y_%m_%d_%H_%M_%S")
        with self._lock:
            while True:
                job_id = f"{prefix}_{self._sequence}"
                self._sequence += 1
                try:
                    (self._archive_root / job_id).mkdir()
                except FileExistsError:
                    continue
                return job_id
