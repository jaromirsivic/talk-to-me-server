from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from talk_to_me_server.domain.jobs import Job
from talk_to_me_server.storage.atomic import atomic_write_bytes, atomic_write_json
from talk_to_me_server.storage.paths import contained_path


JOB_ID_PATTERN = re.compile(r"^\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}_\d+$")


class JobArchive:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self._root = root.resolve(strict=True)

    @property
    def root(self) -> Path:
        return self._root

    def create(self, job: Job) -> Path:
        job_directory = self._job_directory(job.id)
        job_directory.mkdir(exist_ok=True)
        contained_path(job_directory, "values").mkdir(exist_ok=True)
        atomic_write_json(
            contained_path(job_directory, "request.json"),
            job.request.model_dump(mode="json", by_alias=True),
        )
        atomic_write_json(contained_path(job_directory, "job.json"), job.to_dict())
        return job_directory

    def write_value_wav(self, job_id: str, index: int, data: bytes) -> Path:
        if not 0 <= index <= 254:
            raise ValueError("value index must be between 0 and 254")
        values_directory = contained_path(self._job_directory(job_id), "values")
        values_directory.mkdir(exist_ok=True)
        destination = contained_path(values_directory, f"{index:03d}.wav")
        atomic_write_bytes(destination, data)
        return destination

    def value_path(self, job_id: str, index: int) -> Path:
        if not 0 <= index <= 254:
            raise ValueError("value index must be between 0 and 254")
        values_directory = contained_path(self._job_directory(job_id), "values")
        values_directory.mkdir(exist_ok=True)
        return contained_path(values_directory, f"{index:03d}.wav")

    def finalize(self, job: Job) -> None:
        atomic_write_json(contained_path(self._job_directory(job.id), "job.json"), job.to_dict())

    def load(self, job_id: str) -> dict[str, Any]:
        path = contained_path(self._job_directory(job_id), "job.json")
        return json.loads(path.read_text(encoding="utf-8"))

    def _job_directory(self, job_id: str) -> Path:
        if not JOB_ID_PATTERN.fullmatch(job_id):
            raise ValueError(f"invalid job ID: {job_id!r}")
        return contained_path(self._root, job_id)
