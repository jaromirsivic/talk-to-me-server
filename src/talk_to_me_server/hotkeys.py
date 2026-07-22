from __future__ import annotations

from collections.abc import Callable
import logging
from threading import Thread, current_thread
from typing import Any


LOGGER = logging.getLogger("talk_to_me_server")
STOP_SHORTCUT = "<ctrl>+<shift>+x"


def _pynput_listener(bindings: dict[str, Callable[[], None]]) -> Any:
    from pynput.keyboard import GlobalHotKeys

    return GlobalHotKeys(bindings)


class GlobalStopHotkey:
    """Best-effort adapter around the platform keyboard listener."""

    def __init__(
        self,
        *,
        listener_factory: Callable[[dict[str, Callable[[], None]]], Any] | None = None,
    ) -> None:
        self._listener_factory = listener_factory or _pynput_listener
        self._listener: Any | None = None
        self._monitor: Thread | None = None
        self._stopping = False

    def start(self, callback: Callable[[], None]) -> None:
        if self._listener is not None:
            return

        def guarded_callback() -> None:
            try:
                callback()
            except Exception:
                LOGGER.exception(
                    "Global stop hotkey callback failed",
                    extra={"component": "hotkey", "event": "hotkey.callback_failed"},
                )

        listener = self._listener_factory({STOP_SHORTCUT: guarded_callback})
        self._stopping = False
        self._listener = listener
        try:
            listener.start()
        except Exception:
            self._listener = None
            try:
                listener.stop()
            except Exception:
                pass
            raise

        self._monitor = Thread(
            target=self._monitor_listener,
            args=(listener,),
            name="talk-to-me-hotkey-monitor",
            daemon=True,
        )
        self._monitor.start()

    def stop(self) -> None:
        listener = self._listener
        if listener is None:
            return
        self._stopping = True
        try:
            listener.stop()
        finally:
            monitor = self._monitor
            if monitor is not None and monitor is not current_thread():
                monitor.join(timeout=1)
            self._listener = None
            self._monitor = None

    def _monitor_listener(self, listener: Any) -> None:
        try:
            listener.join()
            if not self._stopping:
                LOGGER.warning(
                    "Global stop hotkey listener ended unexpectedly",
                    extra={"component": "hotkey", "event": "hotkey.listener_stopped"},
                )
        except Exception:
            if not self._stopping:
                LOGGER.exception(
                    "Global stop hotkey listener failed",
                    extra={"component": "hotkey", "event": "hotkey.listener_failed"},
                )
