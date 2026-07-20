import os
import wave
from pathlib import Path

import pytest

from talk_to_me_server.tts.piper_engine import PiperEngine


@pytest.mark.real_piper
def test_default_voice_synthesizes_valid_wav(tmp_path: Path) -> None:
    """Requires TALK_TO_ME_SMOKE_ROOT containing the installed default model."""
    root_value = os.environ.get("TALK_TO_ME_SMOKE_ROOT")
    if not root_value:
        pytest.skip("TALK_TO_ME_SMOKE_ROOT is not set")
    voice_root = (
        Path(root_value)
        / "data"
        / "voices"
        / "official"
        / "en_US-ljspeech-medium"
    )
    model = voice_root / "model.onnx"
    config = voice_root / "model.onnx.json"
    if not model.is_file() or not config.is_file():
        pytest.skip("installed default Piper model is missing")

    output = tmp_path / "hello.wav"
    PiperEngine.load(model, config).synthesize("Hello from TalkToMe.", output)

    with wave.open(str(output), "rb") as wav_file:
        assert wav_file.getnframes() > 0
        assert wav_file.getframerate() > 0
        assert wav_file.getnchannels() > 0
