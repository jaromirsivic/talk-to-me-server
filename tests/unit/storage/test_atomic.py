import os

import pytest

from talk_to_me_server.storage.atomic import atomic_write_json


def test_replace_failure_removes_temporary_file(monkeypatch, tmp_path) -> None:
    destination = tmp_path / "value.json"

    def fail_replace(_source, _destination) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        atomic_write_json(destination, {"value": 1})

    assert list(tmp_path.iterdir()) == []
