from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import wave


MAX_PAUSE_MS = 15_000
SAMPLE_RATE = 22_050

# pause-command  := "{{pause(" signed-integer ")}}"
# signed-integer := ("+" | "-")? ASCII-digit+


@dataclass(frozen=True)
class PauseCommand:
    duration_ms: int | None

    @classmethod
    def from_text(cls, text: str) -> PauseCommand | None:
        candidate = text.strip()
        prefix = "{{pause("
        suffix = ")}}"
        if not candidate.startswith(prefix) or not candidate.endswith(suffix):
            return None
        duration = _parse_duration(candidate[len(prefix) : -len(suffix)].strip())
        return cls(duration)


def _parse_duration(value: str) -> int | None:
    if not value:
        return None

    negative = False
    position = 0
    if value[0] in {"+", "-"}:
        negative = value[0] == "-"
        position = 1
    if position == len(value):
        return None

    magnitude = 0
    for character in value[position:]:
        if character not in "0123456789":
            return None
        magnitude = min(
            MAX_PAUSE_MS + 1,
            magnitude * 10 + ord(character) - ord("0"),
        )

    if negative:
        return 0
    return min(magnitude, MAX_PAUSE_MS)


def silence_wav(duration_ms: int) -> bytes:
    if not 0 <= duration_ms <= MAX_PAUSE_MS:
        raise ValueError(f"pause duration must be between 0 and {MAX_PAUSE_MS}")
    frames = (SAMPLE_RATE * duration_ms + 500) // 1_000
    output = BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(b"\x00\x00" * frames)
    return output.getvalue()
