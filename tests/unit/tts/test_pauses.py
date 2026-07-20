from io import BytesIO
import wave

import pytest

from talk_to_me_server.tts.pauses import PauseCommand, silence_wav


@pytest.mark.parametrize(
    ("text", "expected_duration"),
    [
        ("{{pause(1000)}}", 1_000),
        ("  {{pause(0)}}\n", 0),
        ("{{pause(-20)}}", 0),
        ("{{pause(+20)}}", 20),
        ("{{pause(15001)}}", 15_000),
        ("{{pause(999999999999999999999999999999)}}", 15_000),
    ],
)
def test_pause_grammar_parses_and_clamps_integer_durations(
    text: str, expected_duration: int
) -> None:
    assert PauseCommand.from_text(text) == PauseCommand(expected_duration)


@pytest.mark.parametrize(
    "text",
    [
        "{{pause()}}",
        "{{pause(1.5)}}",
        "{{pause(ONE)}}",
        "{{pause(10,20)}}",
    ],
)
def test_pause_grammar_recognizes_invalid_commands_as_zero_audio(text: str) -> None:
    assert PauseCommand.from_text(text) == PauseCommand(None)


@pytest.mark.parametrize(
    "text",
    [
        "other item with {{pause(1000)}}",
        "{{Pause(1000)}}",
        "{{PAUSE}}",
        "{{pause(1000)}} after",
        "ordinary text",
    ],
)
def test_pause_grammar_leaves_noncommands_for_synthesis(text: str) -> None:
    assert PauseCommand.from_text(text) is None


@pytest.mark.parametrize(
    ("duration_ms", "expected_frames"),
    [(0, 0), (1, 22), (100, 2_205), (1_000, 22_050), (15_000, 330_750)],
)
def test_silence_wav_has_requested_duration(
    duration_ms: int, expected_frames: int
) -> None:
    with wave.open(BytesIO(silence_wav(duration_ms)), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getframerate() == 22_050
        assert wav_file.getsampwidth() == 2
        assert wav_file.getnframes() == expected_frames
        assert set(wav_file.readframes(expected_frames)) <= {0}
