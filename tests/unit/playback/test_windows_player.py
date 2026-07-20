import asyncio
import threading
import time
import wave

import numpy as np
import pytest

from talk_to_me_server.playback.base import PlaybackValue
from talk_to_me_server.playback.windows import (
    WindowsAudioPlayer,
    _BufferedValue,
    _StreamState,
)
from talk_to_me_server.tts.pauses import silence_wav


class CallbackStop(Exception):
    pass


class _Status:
    output_underflow = False


class FakeOutputStream:
    def __init__(
        self,
        owner,
        *,
        channels,
        callback,
        finished_callback,
        **_kwargs,
    ) -> None:
        self.owner = owner
        self.channels = channels
        self.callback = callback
        self.finished_callback = finished_callback
        self.thread = None
        self.aborted = False

    def start(self) -> None:
        def run() -> None:
            for _ in range(2_000):
                if self.aborted:
                    return
                block = np.full(
                    (self.owner.block_frames, self.channels),
                    np.nan,
                    dtype=np.float32,
                )
                try:
                    self.callback(block, len(block), None, _Status())
                except CallbackStop:
                    self.owner.blocks.append(block.copy())
                    self.finished_callback()
                    return
                self.owner.blocks.append(block.copy())
                time.sleep(0.001)
            raise AssertionError("stream did not stop")

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def abort(self) -> None:
        self.aborted = True

    def close(self) -> None:
        if self.thread is not None:
            self.thread.join(timeout=2)


class FakeSoundDevice:
    CallbackStop = CallbackStop

    def __init__(self, *, block_frames: int = 4) -> None:
        self.block_frames = block_frames
        self.blocks: list[np.ndarray] = []
        self.stream_kwargs = None

    def OutputStream(self, **kwargs):
        self.stream_kwargs = kwargs
        return FakeOutputStream(self, **kwargs)


def _wav(path, samples, *, sample_rate=22_050) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(np.array(samples, dtype=np.int16).tobytes())


@pytest.mark.asyncio
async def test_stream_callback_joins_ready_values_inside_one_output_block() -> None:
    loop = asyncio.get_running_loop()
    state = _StreamState(loop, CallbackStop, max_buffered_values=2)
    state.append(_BufferedValue(0, np.array([[0.1], [0.2]], dtype=np.float32)))
    state.append(_BufferedValue(1, np.array([[0.3], [0.4]], dtype=np.float32)))
    state.finish_source()
    output = np.zeros((4, 1), dtype=np.float32)

    with pytest.raises(CallbackStop):
        state.callback(output, 4, None, _Status())

    assert output[:, 0] == pytest.approx([0.1, 0.2, 0.3, 0.4])


@pytest.mark.asyncio
async def test_windows_player_scales_samples_and_drains_stream(tmp_path) -> None:
    path = tmp_path / "sample.wav"
    _wav(path, [-32_767, 32_767])
    sounddevice = FakeSoundDevice(block_frames=4)
    events = []

    async def values():
        yield PlaybackValue(0, path)

    async def started(index):
        events.append(("started", index))

    async def finished(index):
        events.append(("finished", index))

    await WindowsAudioPlayer(sounddevice).play(values(), 50, started, finished)

    assert sounddevice.stream_kwargs["samplerate"] == 22_050
    assert sounddevice.stream_kwargs["blocksize"] == 0
    assert sounddevice.blocks[0][:2, 0] == pytest.approx([-0.5, 0.5], abs=0.01)
    assert events == [("started", 0), ("finished", 0)]


@pytest.mark.asyncio
async def test_windows_player_outputs_only_live_silence_while_next_value_is_pending(
    tmp_path,
) -> None:
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    _wav(first, [16_384, 16_384])
    _wav(second, [-16_384, -16_384])
    release_second = asyncio.Event()
    sounddevice = FakeSoundDevice(block_frames=2)
    events = []

    async def values():
        yield PlaybackValue(0, first)
        await release_second.wait()
        yield PlaybackValue(1, second)

    async def started(index):
        events.append(("started", index))

    async def finished(index):
        events.append(("finished", index))

    playback = asyncio.create_task(
        WindowsAudioPlayer(sounddevice).play(values(), 100, started, finished)
    )
    while ("finished", 0) not in events:
        await asyncio.sleep(0.001)
    await asyncio.sleep(0.01)
    release_second.set()
    await asyncio.wait_for(playback, timeout=2)

    first_block = next(
        index for index, block in enumerate(sounddevice.blocks) if np.max(block) > 0.4
    )
    second_block = next(
        index for index, block in enumerate(sounddevice.blocks) if np.min(block) < -0.4
    )
    assert second_block > first_block + 1
    assert all(
        np.allclose(block, 0)
        for block in sounddevice.blocks[first_block + 1 : second_block]
    )
    assert events == [
        ("started", 0),
        ("finished", 0),
        ("started", 1),
        ("finished", 1),
    ]


@pytest.mark.asyncio
async def test_windows_player_rejects_out_of_range_volume() -> None:
    async def values():
        if False:
            yield

    async def event(_index):
        return None

    with pytest.raises(ValueError, match="between 0 and 100"):
        await WindowsAudioPlayer(FakeSoundDevice()).play(values(), 101, event, event)


@pytest.mark.asyncio
async def test_windows_player_finishes_zero_duration_pause(tmp_path) -> None:
    path = tmp_path / "pause.wav"
    path.write_bytes(silence_wav(0))
    sounddevice = FakeSoundDevice()
    events = []

    async def values():
        yield PlaybackValue(0, path)

    async def started(index):
        events.append(("started", index))

    async def finished(index):
        events.append(("finished", index))

    await WindowsAudioPlayer(sounddevice).play(values(), 100, started, finished)

    assert events == [("started", 0), ("finished", 0)]
