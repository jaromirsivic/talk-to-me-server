import json

import pytest


@pytest.mark.parametrize("values", [None, []])
def test_empty_values_is_a_successful_no_op(tts_client, values) -> None:
    response = tts_client.post("/api/v1/textToSpeech", json={"values": values})

    assert response.status_code == 200
    assert response.json() == {
        "version": 1,
        "reasonCode": 200,
        "reasonText": "No values to process",
    }


def test_empty_singular_value_is_a_successful_no_op(tts_client) -> None:
    response = tts_client.post("/api/v1/textToSpeech", json={"value": ""})

    assert response.status_code == 200
    assert response.json()["reasonText"] == "No values to process"


def test_waiting_client_gets_terminal_snapshot_then_job_is_released(
    tts_client, tts_runtime
) -> None:
    response = tts_client.post(
        "/api/v1/textToSpeech",
        json={
            "values": ["one", "two"],
            "calculateStats": True,
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["job"]["state"] == "finished"
    assert "workerIndex" not in body["job"]
    assert "totalWorkers" not in body["job"]
    for value in body["job"]["values"]:
        assert list(value)[:4] == ["id", "index", "workerIndex", "totalWorkers"]
        assert value["workerIndex"] == 0
        assert value["totalWorkers"] == 4
    assert body["stats"]["items"] == 2
    assert body["stats"]["characters"] == 6
    assert tts_runtime.queue.get(body["job"]["id"]) is None


def test_worker_metadata_is_omitted_without_calculate_stats(tts_client) -> None:
    response = tts_client.post(
        "/api/v1/textToSpeech",
        json={"values": ["one"], "waitUntilPlaybackFinished": True},
    )

    assert response.status_code == 200
    value = response.json()["job"]["values"][0]
    assert "workerIndex" not in value
    assert "totalWorkers" not in value


def test_volume_multiplier_scales_the_chosen_volume_for_playback(
    tts_client, tts_runtime
) -> None:
    original = tts_runtime.playback.player.play
    observed = []

    async def capture_volume(values, volume, on_started, on_finished):
        observed.append(volume)
        await original(values, volume, on_started, on_finished)

    tts_runtime.playback.player.play = capture_volume
    response = tts_client.post(
        "/api/v1/textToSpeech",
        json={
            "value": "hello",
            "volumeMultiplier": 0.505,
            "waitUntilPlaybackFinished": True,
        },
    )

    assert response.status_code == 200
    assert observed == [51]
    assert response.json()["job"]["snapshot"]["volume"] == 51


def test_standalone_play_commands_play_assets_without_synthesis(
    tts_client, tts_runtime
) -> None:
    response = tts_client.post(
        "/api/v1/textToSpeech",
        json={
            "values": [
                "item1",
                "{{play('positive_gong.wav')}}",
                "{{play('neutral_gong.wav')}}",
                " {{play('negative_gong.wav')}} ",
                "{{Play('positive_gong.wav')}}",
                "{{POSITIVE_GONG}}",
                "other item with {{play('neutral_gong.wav')}}",
                "itemN",
            ],
            "calculateStats": True,
        },
    )

    assert response.status_code == 200
    assert tts_runtime.playback.player.played == [
        "item1",
        "sound:1",
        "sound:2",
        "sound:3",
        "{{Play('positive_gong.wav')}}",
        "{{POSITIVE_GONG}}",
        "other item with {{play('neutral_gong.wav')}}",
        "itemN",
    ]
    values = response.json()["job"]["values"]
    assert [value["workerIndex"] for value in values] == [
        0, None, None, None, 0, 0, 0, 0
    ]


def test_pause_commands_play_silence_in_order_without_synthesis(
    tts_client, tts_runtime
) -> None:
    response = tts_client.post(
        "/api/v1/textToSpeech",
        json={
            "values": [
                "item1",
                "{{pause(1000)}}",
                "{{pause(-50)}}",
                "{{pause(20000)}}",
                "{{pause(INVALID)}}",
                "{{Pause(500)}}",
                "{{PAUSE_500}}",
                "other item with {{pause(1000)}}",
                "itemN",
            ],
            "calculateStats": True,
        },
    )

    assert response.status_code == 200
    assert tts_runtime.playback.player.played == [
        "item1",
        "pause:1000ms",
        "pause:15000ms",
        "{{Pause(500)}}",
        "{{PAUSE_500}}",
        "other item with {{pause(1000)}}",
        "itemN",
    ]
    assert tts_runtime.playback.player.received_indices == [0, 1, 3, 5, 6, 7, 8]
    values = response.json()["job"]["values"]
    assert [value["workerIndex"] for value in values] == [
        0,
        None,
        None,
        None,
        None,
        0,
        0,
        0,
        0,
    ]


def test_singular_value_is_split_into_sentences_and_tokens_before_queueing(
    tts_client, tts_runtime
) -> None:
    original = (
        "First sentence. Second sentence? Text before {{play('positive_gong.wav')}}"
        " after, {{pause(500)}}, final sentence."
    )
    response = tts_client.post(
        "/api/v1/textToSpeech",
        json={"value": original, "calculateStats": True},
    )

    assert response.status_code == 200
    expected = [
        "First sentence.",
        " Second sentence?",
        " Text before ",
        "{{play('positive_gong.wav')}}",
        " after, ",
        "{{pause(500)}}",
        ", final sentence.",
    ]
    assert [item["text"] for item in response.json()["job"]["values"]] == expected
    assert tts_runtime.playback.player.played == [
        "First sentence.",
        " Second sentence?",
        " Text before ",
        "sound:1",
        " after, ",
        "pause:500ms",
        ", final sentence.",
    ]
    job_id = response.json()["job"]["id"]
    archived = json.loads(
        (tts_runtime.archive.root / job_id / "request.json").read_text(
            encoding="utf-8"
        )
    )
    assert archived["values"] == expected
    assert "value" not in archived


def test_nonwaiting_response_contains_job_id_after_request_is_archived(
    tts_client, tts_runtime
) -> None:
    response = tts_client.post("/api/v1/textToSpeech", json={"values": ["hello"]})
    job_id = response.json()["jobId"]

    assert response.status_code == 200
    request_path = tts_runtime.archive.root / job_id / "request.json"
    archived_request = json.loads(request_path.read_text(encoding="utf-8"))
    assert archived_request["importance"] == "high"
    assert archived_request["volumeMultiplier"] == 1.0
    assert "severity" not in archived_request


def test_legacy_severity_is_rejected(tts_client) -> None:
    response = tts_client.post(
        "/api/v1/textToSpeech",
        json={"values": ["hello"], "severity": "info"},
    )

    assert response.status_code == response.json()["reasonCode"] == 400


def test_missing_values_is_400_but_shape_overflow_is_413(tts_client) -> None:
    missing = tts_client.post("/api/v1/textToSpeech", json={})
    too_many = tts_client.post("/api/v1/textToSpeech", json={"values": ["x"] * 256})
    too_long = tts_client.post(
        "/api/v1/textToSpeech", json={"values": ["x" * 16_385]}
    )
    values_as_string = tts_client.post(
        "/api/v1/textToSpeech", json={"values": "not an array"}
    )
    both = tts_client.post(
        "/api/v1/textToSpeech", json={"value": "one", "values": ["two"]}
    )
    split_overflow = tts_client.post(
        "/api/v1/textToSpeech", json={"value": "Sentence. " * 256}
    )

    assert missing.status_code == missing.json()["reasonCode"] == 400
    assert too_many.status_code == too_many.json()["reasonCode"] == 413
    assert too_long.status_code == too_long.json()["reasonCode"] == 413
    assert values_as_string.status_code == values_as_string.json()["reasonCode"] == 400
    assert both.status_code == both.json()["reasonCode"] == 400
    assert split_overflow.status_code == split_overflow.json()["reasonCode"] == 413
