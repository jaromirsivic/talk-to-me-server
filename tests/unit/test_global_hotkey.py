from __future__ import annotations

import logging
from threading import Event

from talk_to_me_server.hotkeys import GlobalStopHotkey


class FakeListener:
    def __init__(self, bindings) -> None:
        self.bindings = bindings
        self.started = False
        self.stopped = Event()

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped.set()

    def join(self) -> None:
        self.stopped.wait(timeout=1)


def test_global_hotkey_registers_ctrl_shift_x_and_invokes_callback() -> None:
    created = []
    activated = []

    def factory(bindings):
        listener = FakeListener(bindings)
        created.append(listener)
        return listener

    hotkey = GlobalStopHotkey(listener_factory=factory)
    hotkey.start(lambda: activated.append(True))

    assert created[0].started is True
    assert list(created[0].bindings) == ["<ctrl>+<shift>+x"]
    created[0].bindings["<ctrl>+<shift>+x"]()
    assert activated == [True]

    hotkey.stop()
    assert created[0].stopped.is_set()


def test_global_hotkey_contains_callback_failures(caplog) -> None:
    created = []

    def factory(bindings):
        listener = FakeListener(bindings)
        created.append(listener)
        return listener

    def fail() -> None:
        raise RuntimeError("callback failed")

    logger = logging.getLogger("talk_to_me_server")
    logger.addHandler(caplog.handler)
    try:
        hotkey = GlobalStopHotkey(listener_factory=factory)
        hotkey.start(fail)
        created[0].bindings["<ctrl>+<shift>+x"]()
        hotkey.stop()
    finally:
        logger.removeHandler(caplog.handler)

    assert "Global stop hotkey callback failed" in caplog.text
