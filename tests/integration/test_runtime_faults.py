from concurrent.futures.process import BrokenProcessPool
import wave

from starlette.testclient import TestClient

from talk_to_me_server.app import create_app
from talk_to_me_server.tts.sounds import SoundLibrary


def test_partial_synthesis_failure_returns_stats_and_releases_waiter(
    tts_client, tts_runtime
) -> None:
    original = tts_runtime.scheduler.pool.synthesize

    async def fail_second(command):
        if command.index == 1:
            raise RuntimeError("onnx failure")
        return await original(command)

    tts_runtime.scheduler.pool.synthesize = fail_second

    response = tts_client.post(
        "/api/v1/textToSpeech",
        json={"values": ["one", "two"], "calculateStats": True},
    )
    body = response.json()

    assert response.status_code == response.json()["reasonCode"] == 500
    assert body["job"]["state"] == "failed"
    assert body["job"]["errors"][0]["valueIndex"] == 1
    assert body["stats"]["perValue"][0]["synthesisDurationMs"] is not None
    assert tts_runtime.queue.get(body["job"]["id"]) is None


def test_broken_worker_pool_is_reported_as_503(tts_client, tts_runtime) -> None:
    async def unavailable(_command):
        raise BrokenProcessPool("worker exited")

    tts_runtime.scheduler.pool.synthesize = unavailable

    response = tts_client.post(
        "/api/v1/textToSpeech",
        json={"values": ["one"], "waitUntilPlaybackFinished": True},
    )

    assert response.status_code == response.json()["reasonCode"] == 503
    assert response.json()["job"]["errors"][0]["component"] == "synthesis"


def test_missing_sound_asset_reports_a_meaningful_error(
    tts_client, tts_runtime, tmp_path
) -> None:
    tts_runtime.scheduler.sounds = SoundLibrary(tmp_path / "missing-sounds")

    response = tts_client.post(
        "/api/v1/textToSpeech",
        json={
            "values": ["{{play('neutral_gong.wav')}}"],
            "waitUntilPlaybackFinished": True,
        },
    )

    assert response.status_code == response.json()["reasonCode"] == 404
    error = response.json()["job"]["errors"][0]
    assert error["valueIndex"] == 0
    assert error["component"] == "sound"
    assert error["message"] == "Sound file was not found: neutral_gong.wav"


def test_sound_path_cannot_escape_the_configured_directory(
    tts_client, tts_runtime, tmp_path
) -> None:
    tts_runtime.scheduler.sounds = SoundLibrary(tmp_path / "sounds")

    response = tts_client.post(
        "/api/v1/textToSpeech",
        json={
            "values": ["{{play('../outside.wav')}}"],
            "calculateStats": True,
        },
    )

    assert response.status_code == response.json()["reasonCode"] == 400
    error = response.json()["job"]["errors"][0]
    assert error["component"] == "sound"
    assert error["message"] == "Sound path points outside master-data/sounds"


def test_wrong_sound_format_is_reported_in_job_errors(
    tts_client, tts_runtime, tmp_path
) -> None:
    root = tmp_path / "sounds"
    root.mkdir(exist_ok=True)
    with wave.open(str(root / "stereo.wav"), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22_050)
        wav_file.writeframes(b"\x00\x00\x00\x00")
    tts_runtime.scheduler.sounds = SoundLibrary(root)

    response = tts_client.post(
        "/api/v1/textToSpeech",
        json={
            "values": ["{{play('stereo.wav')}}"],
            "calculateStats": True,
        },
    )

    assert response.status_code == response.json()["reasonCode"] == 400
    error = response.json()["job"]["errors"][0]
    assert error["component"] == "sound"
    assert error["message"] == "Sound must be mono 22050 Hz WAV: stereo.wav"


def test_audio_is_retried_up_to_three_attempts(tts_client, tts_runtime) -> None:
    original = tts_runtime.playback.player.play
    attempts = 0

    async def temporarily_unavailable(values, volume, on_started, on_finished):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise OSError("device busy")
        await original(values, volume, on_started, on_finished)

    tts_runtime.playback.player.play = temporarily_unavailable

    response = tts_client.post(
        "/api/v1/textToSpeech",
        json={"values": ["one"], "waitUntilPlaybackFinished": True},
    )

    assert response.status_code == 200
    assert attempts == 3


def test_exhausted_audio_retries_are_reported_as_503(tts_client, tts_runtime) -> None:
    attempts = 0

    async def unavailable(_values, _volume, _on_started, _on_finished):
        nonlocal attempts
        attempts += 1
        raise OSError("device busy")

    tts_runtime.playback.player.play = unavailable

    response = tts_client.post(
        "/api/v1/textToSpeech",
        json={"values": ["one"], "waitUntilPlaybackFinished": True},
    )

    assert response.status_code == response.json()["reasonCode"] == 503
    assert attempts == 3
    assert response.json()["job"]["errors"][0]["message"] == "Audio playback unavailable"


def test_unexpected_api_error_is_sanitized_and_has_correlation_id(runtime) -> None:
    class BrokenCatalog:
        def list(self):
            raise RuntimeError("secret internal detail")

    runtime.voice_catalog = BrokenCatalog()
    with TestClient(
        create_app(runtime),
        client=("127.0.0.1", 50_000),
        raise_server_exceptions=False,
    ) as client:
        response = client.post("/api/v1/getVoices", json={})

    assert response.status_code == response.json()["reasonCode"] == 500
    assert response.json()["reasonText"] == "Internal server error"
    assert "secret" not in response.text
    assert response.json()["correlationId"] == response.headers["x-correlation-id"]
