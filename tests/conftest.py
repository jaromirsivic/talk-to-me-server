from pathlib import Path

import pytest
from starlette.testclient import TestClient

from talk_to_me_server.app import create_app
from talk_to_me_server.config.models import Settings
from talk_to_me_server.config.service import SettingsService
from talk_to_me_server.lifespan import Runtime


MASTER_SETUP = Path("master-data/setup.json")


@pytest.fixture
def approved_settings() -> Settings:
    return Settings.model_validate_json(MASTER_SETUP.read_text(encoding="utf-8"))


@pytest.fixture
def loopback_only_settings(approved_settings: Settings) -> Settings:
    return approved_settings.model_copy(
        update={
            "network": approved_settings.network.model_copy(
                update={"remote_management_enabled": False}
            )
        }
    )


@pytest.fixture
def runtime(tmp_path, approved_settings) -> Runtime:
    service = SettingsService(tmp_path / "setup.json", approved_settings)
    service.initialize()
    return Runtime(settings=service, startup_settings=service.current())


@pytest.fixture
def app(runtime):
    return create_app(runtime)


@pytest.fixture
def client(app):
    with TestClient(app, client=("127.0.0.1", 50_000)) as test_client:
        yield test_client


@pytest.fixture
def remote_client(app):
    with TestClient(app, client=("192.168.1.50", 50_000)) as test_client:
        yield test_client
