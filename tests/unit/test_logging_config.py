import json
import logging
from pathlib import Path

from talk_to_me_server.logging_config import JsonFormatter, configure_logging


def test_json_formatter_emits_structured_context_without_message_text() -> None:
    record = logging.LogRecord("test", logging.INFO, "", 0, "worker started", (), None)
    record.component = "synthesis"
    record.event = "worker.started"
    record.job_id = "job-1"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["component"] == "synthesis"
    assert payload["event"] == "worker.started"
    assert payload["jobId"] == "job-1"
    assert "text" not in payload


def test_logging_uses_utf8_rotating_file(tmp_path: Path) -> None:
    logger = configure_logging(tmp_path)
    logger.info("configured", extra={"component": "runtime", "event": "runtime.started"})

    content = (tmp_path / "server.jsonl").read_text(encoding="utf-8")
    assert json.loads(content)["event"] == "runtime.started"
