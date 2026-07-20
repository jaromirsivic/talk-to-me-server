import json

import pytest

from talk_to_me_server.tts.text_segmenter import PiperTextSegmenter, split_text


def test_espeak_sentence_boundaries_preserve_text_and_decimal_points() -> None:
    assert split_text(
        "First sentence. Second sentence? Value 3.14 is pi! Last fragment",
        phoneme_type="espeak",
        espeak_voice="en-us",
    ) == [
        "First sentence.",
        " Second sentence?",
        " Value 3.14 is pi!",
        " Last fragment",
    ]


def test_espeak_keeps_ellipsis_and_clause_punctuation_inside_sentence() -> None:
    assert split_text(
        "Wait... still here; yes: continuing, then done. Next!?!",
        phoneme_type="espeak",
        espeak_voice="en-us",
    ) == [
        "Wait... still here; yes: continuing, then done.",
        " Next!?!",
    ]


def test_espeak_paragraph_boundary_without_punctuation_is_preserved() -> None:
    assert split_text(
        "First paragraph\ncontinues here\n\nSecond paragraph.",
        phoneme_type="espeak",
        espeak_voice="en-us",
    ) == [
        "First paragraph\ncontinues here\n\n",
        "Second paragraph.",
    ]


def test_special_tokens_are_isolated_before_sentence_segmentation() -> None:
    assert split_text(
        "First. Before {{play('positive_gong.wav')}} after, {{pause(500)}}, final.",
        phoneme_type="espeak",
        espeak_voice="en-us",
    ) == [
        "First.",
        " Before ",
        "{{play('positive_gong.wav')}}",
        " after, ",
        "{{pause(500)}}",
        ", final.",
    ]


def test_clause_before_token_is_not_split_at_its_last_comma() -> None:
    assert split_text(
        "First. A clause, which continues {{pause(500)}} after it.",
        phoneme_type="espeak",
        espeak_voice="en-us",
    ) == [
        "First.",
        " A clause, which continues ",
        "{{pause(500)}}",
        " after it.",
    ]


def test_unknown_braced_text_remains_speech() -> None:
    assert split_text(
        "Speak {{UNKNOWN_TOKEN}} normally.",
        phoneme_type="espeak",
        espeak_voice="en-us",
    ) == ["Speak {{UNKNOWN_TOKEN}} normally."]


def test_text_phoneme_voice_keeps_each_non_token_span_whole() -> None:
    assert split_text(
        "First. {{pause(500)}} Second.",
        phoneme_type="text",
    ) == ["First. ", "{{pause(500)}}", " Second."]


@pytest.mark.asyncio
async def test_segmenter_reads_the_selected_voice_configuration(tmp_path) -> None:
    config = tmp_path / "voice.onnx.json"
    config.write_text(
        json.dumps({"phoneme_type": "espeak", "espeak": {"voice": "en-us"}}),
        encoding="utf-8",
    )
    requested = []
    segmenter = PiperTextSegmenter(
        lambda speaker: requested.append(speaker) or config
    )

    values = await segmenter.split("One. Two?", "selected-voice")

    assert values == ["One.", " Two?"]
    assert requested == ["selected-voice"]
