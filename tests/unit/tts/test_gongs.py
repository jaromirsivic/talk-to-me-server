from pathlib import Path
import wave

import pytest

from talk_to_me_server.tts.sounds import PlayCommand, SoundLibrary


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("{{play('positive_gong.wav')}}", PlayCommand("positive_gong.wav")),
        ("  {{play(\"nested/neutral_gong.wav\")}}\n", PlayCommand("nested/neutral_gong.wav")),
        ("{{Play('negative_gong.wav')}}", None),
        ("{{POSITIVE_GONG}}", None),
        ("other item with {{play('neutral_gong.wav')}}", None),
        ("{{play('neutral_gong.wav')}} after", None),
        ("ordinary text", None),
    ],
)
def test_play_command_requires_standalone_case_sensitive_syntax(
    text: str, expected: PlayCommand | None
) -> None:
    assert PlayCommand.from_text(text) == expected


def test_library_loads_nested_mono_22050_wav(tmp_path: Path) -> None:
    root = tmp_path / "sounds"
    path = root / "nested" / "sound.wav"
    path.parent.mkdir(parents=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22_050)
        wav_file.writeframes(b"\x00\x00")

    assert SoundLibrary(root).load("nested/sound.wav") == path.read_bytes()


@pytest.mark.parametrize("name", ["positive_gong.wav", "neutral_gong.wav", "negative_gong.wav"])
def test_distributed_sounds_match_the_playback_format(name: str) -> None:
    path = Path("master-data/sounds") / name

    with wave.open(str(path), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getframerate() == 22_050
        assert wav_file.getsampwidth() == 2
        assert wav_file.getcomptype() == "NONE"
        assert wav_file.getnframes() > 0


@pytest.mark.parametrize(
    "name", ["../outside.wav", "..\\outside.wav", "nested/../../outside.wav"]
)
def test_library_rejects_paths_outside_sound_root(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="outside"):
        SoundLibrary(tmp_path / "sounds").load(name)


@pytest.mark.parametrize(("channels", "rate"), [(2, 22_050), (1, 44_100)])
def test_library_rejects_wrong_audio_format(
    tmp_path: Path, channels: int, rate: int
) -> None:
    root = tmp_path / "sounds"
    root.mkdir()
    path = root / "wrong.wav"
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(rate)
        wav_file.writeframes(b"\x00\x00" * channels)

    with pytest.raises(ValueError, match="mono 22050 Hz"):
        SoundLibrary(root).load("wrong.wav")
