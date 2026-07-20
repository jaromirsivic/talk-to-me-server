import json
import os
from datetime import datetime, timedelta, timezone

from talk_to_me_server.storage.garbage_collector import GarbageCollector


NOW = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)


def create_archive(root, job_id: str, state: str, age_seconds: int):
    path = root / job_id
    path.mkdir()
    (path / "job.json").write_text(json.dumps({"state": state}), encoding="utf-8")
    timestamp = (NOW - timedelta(seconds=age_seconds)).timestamp()
    os.utime(path, (timestamp, timestamp))
    return path


def test_collector_deletes_only_old_terminal_inactive_archives(tmp_path) -> None:
    old = create_archive(tmp_path, "2026_07_18_10_00_00_0", "finished", 7_200)
    active = create_archive(tmp_path, "2026_07_18_10_00_00_1", "finished", 7_200)
    processing = create_archive(tmp_path, "2026_07_18_10_00_00_2", "processing", 7_200)
    unknown = create_archive(tmp_path, "notes", "finished", 7_200)
    collector = GarbageCollector(tmp_path, timeout_seconds=3_600)

    report = collector.collect(now=NOW, active_ids={active.name})

    assert report.deleted == (old.name,)
    assert report.skipped_active == (active.name,)
    assert not old.exists()
    assert active.exists() and processing.exists() and unknown.exists()


def test_collector_skips_symlinks(tmp_path) -> None:
    outside = tmp_path / "outside"
    root = tmp_path / "root"
    outside.mkdir()
    root.mkdir()
    target = create_archive(outside, "2026_07_18_10_00_00_0", "finished", 7_200)
    link = root / "2026_07_18_10_00_00_0"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        return

    report = GarbageCollector(root, timeout_seconds=0).collect(now=NOW, active_ids=set())

    assert report.deleted == ()
    assert target.exists()
