def test_get_setup_accepts_empty_or_empty_object(client) -> None:
    without_body = client.post("/api/v1/getSetup")
    with_object = client.post("/api/v1/getSetup", json={})

    assert without_body.status_code == with_object.status_code == 200
    assert with_object.json()["setup"]["voice"]["speaker"] == "en_US-ljspeech-medium"
    assert with_object.json()["setup"]["voice"]["language"] == "en_US"
    assert "severity" not in with_object.json()["setup"]["voice"]


def test_set_setup_applies_live_fields_without_restart(client, runtime) -> None:
    current = client.post("/api/v1/getSetup", json={}).json()["setup"]
    current["voice"]["volume"] = 72
    current["general"]["theme"] = "dark"

    response = client.post("/api/v1/setSetup", json={"setup": current})

    assert response.status_code == 200
    assert response.json()["restartRequired"] is False
    assert response.json()["restartFields"] == []
    assert runtime.effective_settings().voice.volume == 72
    assert runtime.effective_settings().general.theme.value == "dark"


def test_set_setup_reports_restart_fields_but_keeps_startup_values(client, runtime) -> None:
    current = client.post("/api/v1/getSetup", json={}).json()["setup"]
    current["general"]["workers"] = 6
    current["network"]["port"] = 5555

    response = client.post("/api/v1/setSetup", json={"setup": current})

    assert response.status_code == 200
    assert response.json()["restartRequired"] is True
    assert response.json()["restartFields"] == ["network.port", "general.workers"]
    assert runtime.settings.current().general.workers == 6
    assert runtime.effective_settings().general.workers == 4
    assert runtime.effective_settings().network.port == 44448


def test_set_setup_requires_setup_wrapper(client) -> None:
    current = client.post("/api/v1/getSetup", json={}).json()["setup"]

    response = client.post("/api/v1/setSetup", json=current)

    assert response.status_code == response.json()["reasonCode"] == 400


def test_set_setup_rejects_legacy_voice_severity(client) -> None:
    current = client.post("/api/v1/getSetup", json={}).json()["setup"]
    current["voice"]["severity"] = {"debug": "accept"}

    response = client.post("/api/v1/setSetup", json={"setup": current})

    assert response.status_code == response.json()["reasonCode"] == 400


def test_set_setup_rederives_language_from_speaker(client, runtime) -> None:
    current = client.post("/api/v1/getSetup", json={}).json()["setup"]
    current["voice"]["speaker"] = "cs_CZ-jirka-medium"
    current["voice"]["language"] = "de_DE"

    response = client.post("/api/v1/setSetup", json={"setup": current})

    assert response.status_code == 200
    assert response.json()["setup"]["voice"]["language"] == "cs_CZ"
    assert runtime.settings.current().voice.language == "cs_CZ"


def test_runtime_limits_are_reported_as_restart_required(client, runtime) -> None:
    current = client.post("/api/v1/getSetup", json={}).json()["setup"]
    current["limits"]["maxQueuedJobs"] = 90
    current["limits"]["maxRequestBodyBytes"] = 32 * 1024 * 1024

    response = client.post("/api/v1/setSetup", json={"setup": current})

    assert response.json()["restartFields"] == [
        "limits.maxQueuedJobs",
        "limits.maxRequestBodyBytes",
    ]
    assert runtime.effective_settings().limits.max_queued_jobs == 100
