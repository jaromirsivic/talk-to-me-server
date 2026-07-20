import asyncio
import threading


def test_playback_is_fifo_without_severity_gongs(
    tts_client, tts_runtime
) -> None:
    original = tts_runtime.scheduler.pool.synthesize
    second_value_started = asyncio.Event()

    async def delayed(command):
        if command.text == "A1":
            await second_value_started.wait()
        elif command.text == "A2":
            second_value_started.set()
        return await original(command)

    tts_runtime.scheduler.pool.synthesize = delayed

    first = tts_client.post(
        "/api/v1/textToSpeech", json={"values": ["A1", "A2"]}
    ).json()["jobId"]
    second_response = tts_client.post(
        "/api/v1/textToSpeech",
        json={"values": ["B1"], "waitUntilPlaybackFinished": True},
    )

    assert second_response.json()["job"]["state"] == "finished"
    assert tts_runtime.playback.player.played == ["A1", "A2", "B1"]
    assert tts_runtime.queue.get(first) is None


def test_first_value_plays_before_second_value_finishes_synthesis(
    tts_client, tts_runtime
) -> None:
    original_synthesize = tts_runtime.scheduler.pool.synthesize
    original_play = tts_runtime.playback.player.play
    release_second = threading.Event()
    first_started = threading.Event()
    first_finished = threading.Event()

    async def delayed_second(command):
        if command.index == 1:
            await asyncio.to_thread(release_second.wait)
        return await original_synthesize(command)

    async def observe_start(values, volume, on_started, on_finished):
        async def observed(index):
            if index == 0:
                first_started.set()
            await on_started(index)

        async def observed_finished(index):
            await on_finished(index)
            if index == 0:
                first_finished.set()

        await original_play(values, volume, observed, observed_finished)

    tts_runtime.scheduler.pool.synthesize = delayed_second
    tts_runtime.playback.player.play = observe_start

    try:
        response = tts_client.post(
            "/api/v1/textToSpeech", json={"values": ["first", "second"]}
        )

        assert response.status_code == 200
        assert first_started.wait(timeout=1)
        assert first_finished.wait(timeout=1)
        assert tts_runtime.playback.player.played == ["first"]
    finally:
        release_second.set()
