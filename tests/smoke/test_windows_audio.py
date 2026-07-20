import asyncio
import os
import sys
import wave
from pathlib import Path

import pytest
import sounddevice

from talk_to_me_server.playback.windows import WindowsAudioPlayer
from talk_to_me_server.playback.base import PlaybackValue


@pytest.mark.windows_audio
def test_opt_in_audio_device_plays_short_sample(tmp_path: Path) -> None:
    """Requires Windows, a working output device, and TALK_TO_ME_AUDIO_SMOKE=1."""
    if sys.platform != "win32":
        pytest.skip("Windows is required")
    if os.environ.get("TALK_TO_ME_AUDIO_SMOKE") != "1":
        pytest.skip("TALK_TO_ME_AUDIO_SMOKE=1 is required")
    sample = tmp_path / "silence.wav"
    with wave.open(str(sample), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(22_050)
        stream.writeframes(b"\0\0" * 2_205)

    async def play() -> None:
        async def values():
            yield PlaybackValue(0, sample)

        async def event(_index: int) -> None:
            return None

        await WindowsAudioPlayer(sounddevice).play(values(), 20, event, event)

    asyncio.run(play())
