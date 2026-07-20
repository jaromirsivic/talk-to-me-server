from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Callable
from pathlib import Path

from talk_to_me_server.tts.pauses import PauseCommand
from talk_to_me_server.tts.sounds import PlayCommand


ConfigResolver = Callable[[str], Path]
Clause = tuple[str, str, bool]
_ESPEAK_LOCK = threading.Lock()
_ESPEAK_INITIALIZED = False


class PiperTextSegmenter:
    def __init__(self, config_resolver: ConfigResolver) -> None:
        self._config_resolver = config_resolver

    async def split(self, text: str, speaker: str) -> list[str]:
        return await asyncio.to_thread(self._split, text, speaker)

    def _split(self, text: str, speaker: str) -> list[str]:
        config_path = self._config_resolver(speaker)
        config = json.loads(config_path.read_text(encoding="utf-8"))
        phoneme_type = str(config.get("phoneme_type", "espeak"))
        espeak = config.get("espeak")
        espeak_voice = (
            str(espeak.get("voice"))
            if isinstance(espeak, dict) and espeak.get("voice")
            else None
        )
        return split_text(
            text,
            phoneme_type=phoneme_type,
            espeak_voice=espeak_voice,
        )


def split_text(
    text: str,
    *,
    phoneme_type: str,
    espeak_voice: str | None = None,
) -> list[str]:
    values: list[str] = []
    for part, special in _split_special_tokens(text):
        if special:
            values.append(part)
            continue
        if not part.strip():
            continue
        if phoneme_type == "espeak":
            if not espeak_voice:
                raise ValueError("Piper voice configuration has no eSpeak voice")
            values.extend(_split_espeak_sentences(part, espeak_voice))
        elif phoneme_type == "pinyin":
            values.extend(_split_pinyin_sentences(part))
        else:
            values.append(part)
    return values


def _split_special_tokens(text: str) -> list[tuple[str, bool]]:
    parts: list[tuple[str, bool]] = []
    cursor = 0
    search_from = 0
    while True:
        start = text.find("{{", search_from)
        if start < 0:
            break
        end = text.find("}}", start + 2)
        if end < 0:
            break
        candidate = text[start : end + 2]
        special = (
            PlayCommand.from_text(candidate) is not None
            or PauseCommand.from_text(candidate) is not None
        )
        if not special:
            search_from = start + 2
            continue
        if start > cursor:
            parts.append((text[cursor:start], False))
        parts.append((candidate, True))
        cursor = end + 2
        search_from = cursor
    if cursor < len(text):
        parts.append((text[cursor:], False))
    return parts


def _split_espeak_sentences(text: str, voice: str) -> list[str]:
    clauses = _espeak_clauses(voice, text)
    boundaries = _map_sentence_boundaries(text, clauses)
    values: list[str] = []
    start = 0
    for boundary in boundaries:
        value = text[start:boundary]
        if value.strip():
            values.append(value)
        start = boundary
    remainder = text[start:]
    if remainder.strip():
        values.append(remainder)
    return values


def _espeak_clauses(voice: str, text: str) -> list[Clause]:
    global _ESPEAK_INITIALIZED

    with _ESPEAK_LOCK:
        if not _ESPEAK_INITIALIZED:
            from piper.phonemize_espeak import EspeakPhonemizer

            EspeakPhonemizer()
            _ESPEAK_INITIALIZED = True
        from piper import espeakbridge

        espeakbridge.set_voice(voice)
        return list(espeakbridge.get_phonemes(text))


def _map_sentence_boundaries(text: str, clauses: list[Clause]) -> list[int]:
    boundaries: list[int] = []
    cursor = 0
    for _phonemes, terminator, end_of_sentence in clauses:
        if terminator:
            position = _find_terminator(text, terminator, cursor)
            if position is None:
                position = text.find(terminator, cursor)
            if position >= 0:
                cursor = position + len(terminator)
        elif end_of_sentence:
            paragraph_end = _find_paragraph_end(text, cursor)
            cursor = paragraph_end if paragraph_end is not None else len(text)

        if not end_of_sentence or cursor <= 0:
            continue
        while cursor < len(text) and text[cursor] in ".?!":
            cursor += 1
        if not boundaries or cursor > boundaries[-1]:
            boundaries.append(cursor)
    return boundaries


def _find_terminator(text: str, terminator: str, start: int) -> int | None:
    position = text.find(terminator, start)
    while position >= 0:
        if terminator != "." or not _ignored_period(text, position):
            return position
        position = text.find(terminator, position + 1)
    return None


def _ignored_period(text: str, position: int) -> bool:
    previous = text[position - 1] if position > 0 else ""
    following = text[position + 1] if position + 1 < len(text) else ""
    if previous == "." or following == ".":
        return True
    if previous.isdigit() and following.isdigit():
        return True
    if previous.isalnum() and following.isalnum():
        return True
    if (
        position >= 3
        and text[position - 2] == "."
        and text[position - 3].isalpha()
        and previous.isalpha()
    ):
        return True
    return False


def _find_paragraph_end(text: str, start: int) -> int | None:
    position = text.find("\n", start)
    while position >= 0:
        cursor = position
        newline_count = 0
        while cursor < len(text):
            if text[cursor] == "\n":
                newline_count += 1
                cursor += 1
                continue
            if text[cursor] in " \t\r":
                cursor += 1
                continue
            break
        if newline_count >= 2:
            return cursor
        position = text.find("\n", position + 1)
    return None


def _split_pinyin_sentences(text: str) -> list[str]:
    from sentence_stream import stream_to_sentences

    return [sentence for sentence in stream_to_sentences([text]) if sentence.strip()]
