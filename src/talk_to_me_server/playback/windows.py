from __future__ import annotations

import asyncio
import logging
import wave
from collections import deque
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np

from talk_to_me_server.playback.base import (
    PlaybackCallback,
    PlaybackValue,
)


LOGGER = logging.getLogger("talk_to_me_server")


@dataclass(frozen=True)
class _AudioFormat:
    sample_rate: int
    channels: int


@dataclass(frozen=True)
class _BufferedValue:
    index: int
    samples: np.ndarray


class _EventKind(StrEnum):
    STARTED = "started"
    FINISHED = "finished"


@dataclass(frozen=True)
class _PlaybackEvent:
    kind: _EventKind
    index: int


class _StreamState:
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        callback_stop: type[BaseException],
        *,
        max_buffered_values: int,
    ) -> None:
        self.loop = loop
        self.callback_stop = callback_stop
        self.max_buffered_values = max_buffered_values
        self.buffers: deque[_BufferedValue] = deque()
        self.current: _BufferedValue | None = None
        self.offset = 0
        self.source_done = False
        self.source_error: BaseException | None = None
        self.events: asyncio.Queue[_PlaybackEvent | None] = asyncio.Queue()
        self.finished = asyncio.Event()
        self.space_available = asyncio.Event()
        self.space_available.set()
        self.output_underflows = 0

    def append(self, value: _BufferedValue) -> None:
        self.buffers.append(value)
        if len(self.buffers) >= self.max_buffered_values:
            self.space_available.clear()

    def finish_source(self, error: BaseException | None = None) -> None:
        self.source_error = error
        self.source_done = True

    def finished_callback(self) -> None:
        self.loop.call_soon_threadsafe(self.finished.set)

    def callback(self, outdata, frames: int, _time, status) -> None:
        if getattr(status, "output_underflow", False):
            self.output_underflows += 1
        outdata.fill(0)
        written = 0
        while written < frames:
            if self.current is None:
                if not self.buffers:
                    if self.source_done:
                        raise self.callback_stop
                    return
                self.current = self.buffers.popleft()
                self.offset = 0
                self.loop.call_soon_threadsafe(self.space_available.set)
                self._emit(_EventKind.STARTED, self.current.index)

            current = self.current
            available = len(current.samples) - self.offset
            count = min(frames - written, available)
            if count:
                outdata[written : written + count] = current.samples[
                    self.offset : self.offset + count
                ]
                written += count
                self.offset += count
            if self.offset == len(current.samples):
                self._emit(_EventKind.FINISHED, current.index)
                self.current = None
                self.offset = 0

        if self.current is None and not self.buffers and self.source_done:
            raise self.callback_stop

    def _emit(self, kind: _EventKind, index: int) -> None:
        self.loop.call_soon_threadsafe(
            self.events.put_nowait, _PlaybackEvent(kind, index)
        )


class WindowsAudioPlayer:
    def __init__(self, sounddevice_module: Any, *, max_buffered_values: int = 2) -> None:
        if max_buffered_values < 1:
            raise ValueError("max_buffered_values must be at least one")
        self._sounddevice = sounddevice_module
        self._max_buffered_values = max_buffered_values
        self._active_stop: asyncio.Event | None = None
        self._active_done: asyncio.Event | None = None

    async def play(
        self,
        values: AsyncIterable[PlaybackValue],
        volume: int,
        on_started: PlaybackCallback,
        on_finished: PlaybackCallback,
    ) -> None:
        if not 0 <= volume <= 100:
            raise ValueError("volume must be between 0 and 100")

        if self._active_done is not None and not self._active_done.is_set():
            raise RuntimeError("audio playback is already active")
        stop_event = asyncio.Event()
        done_event = asyncio.Event()
        self._active_stop = stop_event
        self._active_done = done_event

        try:
            iterator = values.__aiter__()
            try:
                first = await anext(iterator)
            except StopAsyncIteration:
                return
            first_buffer, audio_format = await asyncio.to_thread(
                _read_value, first, volume, None
            )
            if stop_event.is_set():
                return
            loop = asyncio.get_running_loop()
            state = _StreamState(
                loop,
                self._sounddevice.CallbackStop,
                max_buffered_values=self._max_buffered_values,
            )
            state.append(first_buffer)
            producer = asyncio.create_task(
                self._feed(iterator, volume, audio_format, state)
            )
            dispatcher = asyncio.create_task(
                _dispatch_events(state.events, on_started, on_finished)
            )
            stream = None
            completed = False
            finish_waiter = asyncio.create_task(state.finished.wait())
            stop_waiter = asyncio.create_task(stop_event.wait())
            try:
                stream = await asyncio.to_thread(
                    self._sounddevice.OutputStream,
                    samplerate=audio_format.sample_rate,
                    channels=audio_format.channels,
                    dtype="float32",
                    blocksize=0,
                    callback=state.callback,
                    finished_callback=state.finished_callback,
                )
                if stop_event.is_set():
                    return
                await asyncio.to_thread(stream.start)
                done, _ = await asyncio.wait(
                    {finish_waiter, stop_waiter},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if stop_waiter in done:
                    return
                completed = True
                await producer
                await state.events.put(None)
                await dispatcher
                if state.output_underflows:
                    LOGGER.warning(
                        "Audio output underflow detected",
                        extra={
                            "component": "playback",
                            "event": "audio.underflow",
                            "underflows": state.output_underflows,
                        },
                    )
                if state.source_error is not None:
                    raise state.source_error
            finally:
                for waiter in (finish_waiter, stop_waiter):
                    if not waiter.done():
                        waiter.cancel()
                await asyncio.gather(
                    finish_waiter,
                    stop_waiter,
                    return_exceptions=True,
                )
                if not producer.done():
                    producer.cancel()
                    await asyncio.gather(producer, return_exceptions=True)
                if not dispatcher.done():
                    dispatcher.cancel()
                    await asyncio.gather(dispatcher, return_exceptions=True)
                if stream is not None:
                    if not completed:
                        abort = getattr(stream, "abort", None)
                        if abort is not None:
                            await asyncio.to_thread(abort)
                    await asyncio.to_thread(stream.close)
        finally:
            done_event.set()
            if self._active_stop is stop_event:
                self._active_stop = None
                self._active_done = None

    async def stop(self) -> None:
        stop_event = self._active_stop
        done_event = self._active_done
        if stop_event is None or done_event is None:
            return
        stop_event.set()
        await done_event.wait()

    async def _feed(
        self,
        iterator: AsyncIterator[PlaybackValue],
        volume: int,
        audio_format: _AudioFormat,
        state: _StreamState,
    ) -> None:
        try:
            async for value in iterator:
                while len(state.buffers) >= state.max_buffered_values:
                    state.space_available.clear()
                    if len(state.buffers) < state.max_buffered_values:
                        break
                    await state.space_available.wait()
                buffered, _ = await asyncio.to_thread(
                    _read_value, value, volume, audio_format
                )
                state.append(buffered)
        except asyncio.CancelledError:
            state.finish_source()
            raise
        except BaseException as error:
            state.finish_source(error)
        else:
            state.finish_source()


async def _dispatch_events(
    events: asyncio.Queue[_PlaybackEvent | None],
    on_started: PlaybackCallback,
    on_finished: PlaybackCallback,
) -> None:
    while True:
        event = await events.get()
        if event is None:
            return
        callback = on_started if event.kind is _EventKind.STARTED else on_finished
        await callback(event.index)


def _read_value(
    value: PlaybackValue,
    volume: int,
    expected_format: _AudioFormat | None,
) -> tuple[_BufferedValue, _AudioFormat]:
    with wave.open(str(value.path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())
    if sample_width != 2:
        raise ValueError("only 16-bit PCM WAV is supported")
    audio_format = _AudioFormat(sample_rate=sample_rate, channels=channels)
    if expected_format is not None and audio_format != expected_format:
        raise ValueError("all values in a job must use the same audio format")
    samples = np.frombuffer(frames, dtype="<i2").reshape((-1, channels))
    scaled = np.clip(
        samples.astype(np.float32) * (volume / (100.0 * 32_768.0)),
        -1.0,
        1.0,
    )
    return _BufferedValue(index=value.index, samples=scaled), audio_format
