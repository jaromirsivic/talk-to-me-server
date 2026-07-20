from datetime import datetime, timedelta, timezone

import pytest

from talk_to_me_server.domain.ids import JobIdGenerator


def test_id_generator_skips_existing_archive_atomically(tmp_path) -> None:
    now = datetime(2026, 7, 18, 12, 0, tzinfo=timezone(timedelta(hours=2)))
    (tmp_path / "2026_07_18_12_00_00_0").mkdir()
    generator = JobIdGenerator(tmp_path, sequence_start=0)

    job_id = generator.next_id(now)

    assert job_id == "2026_07_18_12_00_00_1"
    assert (tmp_path / job_id).is_dir()


def test_id_generator_requires_timezone_aware_time(tmp_path) -> None:
    generator = JobIdGenerator(tmp_path)

    with pytest.raises(ValueError, match="timezone-aware"):
        generator.next_id(datetime(2026, 7, 18, 12, 0))
