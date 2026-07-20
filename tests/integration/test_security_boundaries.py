import asyncio
from pathlib import Path

import pytest

from talk_to_me_server.config.models import Settings
from talk_to_me_server.config.service import SettingsService
from talk_to_me_server.lifespan import Runtime
from talk_to_me_server.storage.paths import PathEscapeError, contained_path


class UnusedImporter:
    pass


@pytest.fixture
def runtime(tmp_path, loopback_only_settings: Settings) -> Runtime:
    service = SettingsService(tmp_path / "setup.json", loopback_only_settings)
    service.initialize()
    return Runtime(settings=service, startup_settings=service.current())


def test_malformed_multipart_is_a_sanitized_client_error(client, runtime) -> None:
    runtime.voice_importer = UnusedImporter()

    response = client.post(
        "/api/v1/importVoice",
        content=b"--broken\r\nContent-Disposition: form-data\r\n",
        headers={"Content-Type": "multipart/form-data; boundary=broken"},
    )

    assert response.status_code == response.json()["reasonCode"] == 400
    assert "traceback" not in response.text.casefold()


def test_locale_traversal_cannot_expose_other_master_data(client) -> None:
    response = client.get("/master-data/i18n/%2e%2e/setup.json")

    assert response.status_code == 404
    assert "remoteManagementEnabled" not in response.text


def test_resolved_symlink_cannot_escape_storage_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    with pytest.raises(PathEscapeError):
        contained_path(root, "escape", "payload.json")


def test_portal_and_management_api_are_denied_remotely_by_default(
    remote_client,
) -> None:
    portal = remote_client.get("/")
    assert portal.status_code == portal.json()["reasonCode"] == 403
    denied = remote_client.post("/api/v1/getSetup", json={})
    assert denied.status_code == denied.json()["reasonCode"] == 403


@pytest.mark.asyncio
async def test_shutdown_cancels_active_playback_and_closes_player(runtime: Runtime) -> None:
    class Player:
        closed = False

        async def close(self) -> None:
            self.closed = True

    class Playback:
        def __init__(self) -> None:
            self.player = Player()
            self.started = asyncio.Event()

        async def run(self) -> None:
            self.started.set()
            await asyncio.Event().wait()

    playback = Playback()
    runtime.playback = playback
    await runtime.start()
    await playback.started.wait()

    await runtime.stop()

    assert playback.player.closed is True
    assert runtime._tasks == []
