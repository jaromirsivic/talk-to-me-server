from __future__ import annotations

import os
import wave
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from piper import PiperVoice


@dataclass
class PiperEngine:
    voice: PiperVoice

    @classmethod
    def load(cls, model_path: Path, config_path: Path) -> PiperEngine:
        return cls(PiperVoice.load(model_path, config_path))

    def synthesize(self, text: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_name(
            f".{output_path.stem}.{uuid4().hex}.part.wav"
        )
        try:
            with wave.open(str(temporary), "wb") as wav_file:
                self.voice.synthesize_wav(text, wav_file)
            validate_wav(temporary)
            os.replace(temporary, output_path)
        finally:
            temporary.unlink(missing_ok=True)


def validate_wav(path: Path) -> None:
    with wave.open(str(path), "rb") as wav_file:
        if wav_file.getnchannels() < 1:
            raise ValueError("WAV has no channels")
        if wav_file.getframerate() < 1:
            raise ValueError("WAV has invalid sample rate")
        if wav_file.getnframes() < 1:
            raise ValueError("WAV contains no frames")


def load_piper_engine(model_path: Path, config_path: Path) -> PiperEngine:
    return PiperEngine.load(model_path, config_path)
