from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock

import pytest

from talk_to_me_server.config.service import SettingsService
from talk_to_me_server.lifespan import Runtime


class FakeHotkey:
    def __init__(
        self,
        *,
        start_error: Exception | None = None,
        stop_error: Exception | None = None,
    ) -> None:
        self.callback = None
        self.start_error = start_error
        self.stop_error = stop_error
        self.stopped = False

    def start(self, callback) -> None:
        if self.start_error is not None:
            raise self.start_error
        self.callback = callback

    def stop(self) -> None:
        self.stopped = True
        if self.stop_error is not None:
            raise self.stop_error


def make_runtime(tmp_path, approved_settings, hotkey) -> Runtime:
    service = SettingsService(tmp_path / "setup.json", approved_settings)
    service.initialize()
    return Runtime(
        settings=service,
        startup_settings=service.current(),
        global_hotkey=hotkey,
    )


@pytest.mark.asyncio
async def test_hotkey_schedules_stop_on_the_runtime_event_loop(
    tmp_path, approved_settings
) -> None:
    hotkey = FakeHotkey()
    runtime = make_runtime(tmp_path, approved_settings, hotkey)
    runtime.stop_playback = AsyncMock(return_value=3)

    await runtime.start()
    await asyncio.to_thread(hotkey.callback)
    for _ in range(20):
        if runtime.stop_playback.await_count:
            break
        await asyncio.sleep(0)

    runtime.stop_playback.assert_awaited_once_with()
    await runtime.stop()
    assert hotkey.stopped is True


@pytest.mark.asyncio
async def test_hotkey_start_failure_does_not_prevent_runtime_start(
    tmp_path, approved_settings, caplog
) -> None:
    hotkey = FakeHotkey(start_error=RuntimeError("no desktop session"))
    runtime = make_runtime(tmp_path, approved_settings, hotkey)

    logger = logging.getLogger("talk_to_me_server")
    logger.addHandler(caplog.handler)
    try:
        await runtime.start()
        await runtime.stop()
    finally:
        logger.removeHandler(caplog.handler)

    assert "Global stop hotkey is unavailable" in caplog.text


@pytest.mark.asyncio
async def test_hotkey_shutdown_failure_does_not_prevent_runtime_stop(
    tmp_path, approved_settings, caplog
) -> None:
    hotkey = FakeHotkey(stop_error=RuntimeError("listener stuck"))
    runtime = make_runtime(tmp_path, approved_settings, hotkey)

    logger = logging.getLogger("talk_to_me_server")
    logger.addHandler(caplog.handler)
    try:
        await runtime.start()
        await runtime.stop()
    finally:
        logger.removeHandler(caplog.handler)

    assert "Global stop hotkey shutdown failed" in caplog.text


@pytest.mark.asyncio
async def test_hotkey_ignores_auto_repeat_while_stop_is_running(
    tmp_path, approved_settings
) -> None:
    hotkey = FakeHotkey()
    runtime = make_runtime(tmp_path, approved_settings, hotkey)
    release = asyncio.Event()
    started = asyncio.Event()

    async def blocking_stop() -> int:
        started.set()
        await release.wait()
        return 1

    runtime.stop_playback = AsyncMock(side_effect=blocking_stop)
    await runtime.start()

    hotkey.callback()
    await started.wait()
    hotkey.callback()
    await asyncio.sleep(0)
    assert runtime.stop_playback.await_count == 1

    release.set()
    await asyncio.sleep(0)
    await runtime.stop()
