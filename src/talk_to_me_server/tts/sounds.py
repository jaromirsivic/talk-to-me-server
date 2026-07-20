from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import wave


SAMPLE_RATE = 22_050


class SoundCommandError(ValueError):
    """A play command names a sound that cannot be played safely."""


class SoundNotFoundError(SoundCommandError):
    pass


class SoundFormatError(SoundCommandError):
    pass


@dataclass(frozen=True)
class PlayCommand:
    filename: str

    @classmethod
    def from_text(cls, text: str) -> PlayCommand | None:
        candidate = text.strip()
        prefix = "{{play("
        suffix = ")}}"
        if not candidate.startswith(prefix) or not candidate.endswith(suffix):
            return None
        argument = candidate[len(prefix) : -len(suffix)].strip()
        if len(argument) < 2 or argument[0] not in {"'", '"'}:
            return None
        if argument[-1] != argument[0]:
            return None
        return cls(argument[1:-1])


class SoundLibrary:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def load(self, filename: str) -> bytes:
        relative = Path(filename)
        if not filename or relative.is_absolute():
            raise SoundCommandError("Sound path must be relative to master-data/sounds")
        target = (self.root / relative).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as error:
            raise SoundCommandError(
                "Sound path points outside master-data/sounds"
            ) from error
        if not target.is_file():
            raise SoundNotFoundError(f"Sound file was not found: {filename}")
        try:
            data = target.read_bytes()
            with wave.open(BytesIO(data), "rb") as wav_file:
                channels = wav_file.getnchannels()
                sample_rate = wav_file.getframerate()
        except (EOFError, OSError, wave.Error) as error:
            raise SoundFormatError(f"Sound is not a valid WAV file: {filename}") from error
        if channels != 1 or sample_rate != SAMPLE_RATE:
            raise SoundFormatError(
                f"Sound must be mono 22050 Hz WAV: {filename}"
            )
        return data
