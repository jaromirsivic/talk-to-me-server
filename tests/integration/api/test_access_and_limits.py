import pytest
from starlette.testclient import TestClient

from talk_to_me_server.app import create_app
from talk_to_me_server.config.models import Settings
from talk_to_me_server.config.service import SettingsService
from talk_to_me_server.lifespan import Runtime


@pytest.fixture
def runtime(tmp_path, loopback_only_settings: Settings) -> Runtime:
    service = SettingsService(tmp_path / "setup.json", loopback_only_settings)
    service.initialize()
    return Runtime(settings=service, startup_settings=service.current())


def test_management_is_loopback_only_until_server_restart(client, remote_client, runtime) -> None:
    denied = remote_client.post("/api/v1/getSetup", json={})
    assert denied.status_code == denied.json()["reasonCode"] == 403

    current = client.post("/api/v1/getSetup", json={}).json()["setup"]
    current["network"]["remoteManagementEnabled"] = True
    changed = client.post("/api/v1/setSetup", json={"setup": current})
    assert changed.json()["restartFields"] == ["network.remoteManagementEnabled"]
    assert remote_client.post("/api/v1/getSetup", json={}).status_code == 403


def test_api_is_post_only_and_has_no_permissive_cors(client) -> None:
    response = client.get("/api/v1/getSetup", headers={"Origin": "https://example.test"})

    assert response.status_code == response.json()["reasonCode"] == 405
    assert "access-control-allow-origin" not in response.headers


def test_body_larger_than_effective_limit_is_413(tmp_path, approved_settings: Settings) -> None:
    limited = approved_settings.model_copy(
        update={
            "limits": approved_settings.limits.model_copy(
                update={"max_request_body_bytes": 128}
            )
        }
    )
    service = SettingsService(tmp_path / "setup.json", limited)
    service.initialize()
    runtime = Runtime(settings=service, startup_settings=service.current())

    with TestClient(create_app(runtime), client=("127.0.0.1", 50_000)) as test_client:
        response = test_client.post(
            "/api/v1/setSetup",
            content=b"x" * 129,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == response.json()["reasonCode"] == 413


def test_security_headers_are_present(client) -> None:
    response = client.post("/api/v1/getSetup", json={})

    assert response.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in response.headers["content-security-policy"]
