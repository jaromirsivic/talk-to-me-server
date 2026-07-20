import wave

from talk_to_me_server.tts.piper_engine import PiperEngine


class FakeVoice:
    def synthesize_wav(self, text, wav_file) -> None:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22_050)
        wav_file.writeframes(text.encode("utf-8") * 4)


def test_piper_engine_loads_pair_and_atomically_writes_valid_wav(monkeypatch, tmp_path) -> None:
    model = tmp_path / "voice.onnx"
    config = tmp_path / "voice.onnx.json"
    model.write_bytes(b"model")
    config.write_text("{}", encoding="utf-8")
    loaded = []

    def fake_load(model_path, config_path):
        loaded.append((model_path, config_path))
        return FakeVoice()

    monkeypatch.setattr("talk_to_me_server.tts.piper_engine.PiperVoice.load", fake_load)
    engine = PiperEngine.load(model, config)
    output = tmp_path / "speech.wav"

    engine.synthesize("hello", output)

    assert loaded == [(model, config)]
    with wave.open(str(output), "rb") as wav_file:
        assert wav_file.getframerate() == 22_050
        assert wav_file.getnframes() > 0
    assert list(tmp_path.glob("*.part.wav")) == []
