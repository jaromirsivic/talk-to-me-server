import asyncio
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
import uvicorn
from starlette.responses import JSONResponse

from talk_to_me_server.app import create_app
from talk_to_me_server.config.models import Settings
from talk_to_me_server.config.service import SettingsService
from talk_to_me_server.domain.ids import JobIdGenerator
from talk_to_me_server.domain.queue import QueueManager
from talk_to_me_server.lifespan import Runtime
from talk_to_me_server.playback.coordinator import PlaybackCoordinator
from talk_to_me_server.storage.archive import JobArchive
from talk_to_me_server.tts.base import SynthesisCommand, SynthesisResult
from talk_to_me_server.tts.scheduler import SynthesisScheduler
from talk_to_me_server.tts.text_segmenter import split_text
from talk_to_me_server.voices.models import VoiceDescriptor, VoiceStatus


class BrowserSynthesisPool:
    async def synthesize(self, command: SynthesisCommand) -> SynthesisResult:
        command.output_path.parent.mkdir(parents=True, exist_ok=True)
        command.output_path.write_bytes(command.text.encode("utf-8"))
        return SynthesisResult(command.job_id, command.index, command.output_path, 1)


class BrowserAudioPlayer:
    async def play(self, values, _volume: int, on_started, on_finished) -> None:
        async for value in values:
            await on_started(value.index)
            await on_finished(value.index)


class BrowserTextSegmenter:
    async def split(self, text: str, _speaker: str) -> list[str]:
        return split_text(
            text,
            phoneme_type="espeak",
            espeak_voice="en-us",
        )


class BrowserVoiceCatalog:
    def __init__(self) -> None:
        self.voices = [
            VoiceDescriptor(
                id="en_US-ljspeech-medium",
                name="LJSpeech",
                language="en-US",
                quality="medium",
                license="Public Domain",
                source="official",
                status=VoiceStatus.READY,
                model_path=Path("model.onnx"),
                config_path=Path("model.onnx.json"),
            ),
            VoiceDescriptor(
                id="en_US-amy-medium",
                name="Amy",
                language="en-US",
                quality="medium",
                size_bytes=63_000_000,
                license="CC0-1.0",
                source="official",
                status=VoiceStatus.DOWNLOAD_REQUIRED,
                downloadable=True,
                model_url="https://voices.test/amy.onnx",
                config_url="https://voices.test/amy.onnx.json",
                model_sha256="a" * 64,
                config_sha256="b" * 64,
            ),
            VoiceDescriptor(
                id="en_US-locked-medium",
                name="Locked Voice",
                language="en-US",
                quality="medium",
                license=None,
                source="official",
                status=VoiceStatus.DOWNLOAD_REQUIRED,
                downloadable=True,
                requires_license_confirmation=True,
                license_notice="License not approved for redistribution",
            ),
            VoiceDescriptor(
                id="broken-voice",
                name="Broken Voice",
                language="en-US",
                quality="unknown",
                license="Unknown",
                source="official",
                status=VoiceStatus.INVALID,
                blocked_reason="Missing voice metadata",
            ),
        ]

    def list(self):
        return tuple(self.voices)

    def get(self, voice_id: str):
        return next((voice for voice in self.voices if voice.id == voice_id), None)

    def add(self, voice: VoiceDescriptor) -> VoiceDescriptor:
        self.voices = [current for current in self.voices if current.id != voice.id]
        self.voices.append(voice)
        return voice


class BrowserVoiceDownloader:
    def __init__(self, catalog: BrowserVoiceCatalog) -> None:
        self.catalog = catalog

    async def download(
        self, voice_id: str, *, license_confirmed: bool = False
    ) -> VoiceDescriptor:
        voice = self.catalog.get(voice_id)
        if voice.requires_license_confirmation and not license_confirmed:
            raise ValueError(voice.license_notice)
        return self.catalog.add(
            voice.model_copy(
                update={
                    "status": VoiceStatus.READY,
                    "downloadable": False,
                    "model_path": Path("downloaded.onnx"),
                    "config_path": Path("downloaded.onnx.json"),
                }
            )
        )


class BrowserVoiceDeleter:
    def __init__(self, catalog: BrowserVoiceCatalog) -> None:
        self.catalog = catalog

    def delete(self, voice_id: str) -> None:
        voice = self.catalog.get(voice_id)
        if voice is None or voice.status is not VoiceStatus.READY:
            raise ValueError("Voice is not installed")
        if voice.source == "custom":
            self.catalog.voices = [
                current for current in self.catalog.voices if current.id != voice_id
            ]
            return
        self.catalog.add(
            voice.model_copy(
                update={
                    "status": VoiceStatus.DOWNLOAD_REQUIRED,
                    "downloadable": True,
                    "model_path": None,
                    "config_path": None,
                }
            )
        )


class BrowserVoiceImporter:
    def __init__(self, catalog: BrowserVoiceCatalog) -> None:
        self.catalog = catalog

    def import_bytes(
        self,
        _model: bytes,
        _config: bytes,
        *,
        display_name: str,
        license_name: str,
        rights_confirmed: bool,
    ) -> VoiceDescriptor:
        return self._add(display_name, license_name, rights_confirmed)

    def _add(
        self, display_name: str, license_name: str, rights_confirmed: bool
    ) -> VoiceDescriptor:
        if not rights_confirmed:
            raise ValueError("Rights confirmation is required")
        slug = display_name.casefold().replace(" ", "-")
        return self.catalog.add(
            VoiceDescriptor(
                id=f"custom/{slug}",
                name=display_name,
                language="und",
                quality="custom",
                license=license_name,
                source="custom",
                status=VoiceStatus.READY,
                model_path=Path("custom.onnx"),
                config_path=Path("custom.onnx.json"),
            )
        )


@dataclass(frozen=True)
class LiveServer:
    url: str
    process_id: int
    original_process_id: int


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    return {**browser_type_launch_args, "headless": True}


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Keep English locators deterministic while locale resolution remains browser-driven."""
    return {**browser_context_args, "locale": "en-US"}


@pytest.fixture
def live_server(tmp_path: Path):
    settings = Settings.model_validate_json(
        Path("master-data/setup.json").read_text(encoding="utf-8")
    )
    service = SettingsService(tmp_path / "setup.json", settings)
    service.initialize()
    archive = JobArchive(tmp_path / "archive")
    queue = QueueManager(100, JobIdGenerator(archive.root))
    pool = BrowserSynthesisPool()
    player = BrowserAudioPlayer()
    runtime = Runtime(
        settings=service,
        startup_settings=service.current(),
        queue=queue,
        archive=archive,
        scheduler=SynthesisScheduler(queue, archive, pool),
        playback=PlaybackCoordinator(queue, archive, player, retry_delay=0),
        text_segmenter=BrowserTextSegmenter(),
    )
    voice_catalog = BrowserVoiceCatalog()
    runtime.voice_catalog = voice_catalog
    runtime.voice_deleter = BrowserVoiceDeleter(voice_catalog)
    runtime.voice_downloader = BrowserVoiceDownloader(voice_catalog)
    runtime.voice_importer = BrowserVoiceImporter(voice_catalog)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    application = create_app(runtime)

    @application.middleware("http")
    async def delay_setup_for_browser_regression(request, call_next):
        delay = request.headers.get("x-test-setup-delay")
        if delay and request.url.path.endswith(("/getSetup", "/setSetup")):
            await asyncio.sleep(float(delay))
        voice_delay = request.headers.get("x-test-voice-delay")
        if voice_delay and request.url.path.endswith(
            ("/downloadVoice", "/deleteVoice", "/importVoice")
        ):
            await asyncio.sleep(float(voice_delay))
        if (
            request.headers.get("x-test-setup-fail") == "true"
            and request.url.path.endswith("/setSetup")
        ):
            return JSONResponse(
                {"reasonCode": 502, "reasonText": "Delayed setup failure"},
                status_code=502,
            )
        return await call_next(request)

    server = uvicorn.Server(
        uvicorn.Config(application, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=0.2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.02)
    else:
        raise RuntimeError("E2E server did not start")
    try:
        yield LiveServer(url, id(server), id(server))
    finally:
        server.should_exit = True
        thread.join(timeout=10)
