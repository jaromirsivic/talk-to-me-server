from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import sounddevice

from talk_to_me_server.api.access import ManagementAccessPolicy
from talk_to_me_server.bootstrap import bootstrap
from talk_to_me_server.config.models import Settings
from talk_to_me_server.config.service import SettingsService
from talk_to_me_server.domain.ids import JobIdGenerator
from talk_to_me_server.domain.jobs import JobError
from talk_to_me_server.domain.queue import QueueManager, QueueSettingsSnapshot
from talk_to_me_server.hotkeys import GlobalStopHotkey
from talk_to_me_server.logging_config import configure_logging
from talk_to_me_server.playback.coordinator import PlaybackCoordinator
from talk_to_me_server.playback.windows import WindowsAudioPlayer
from talk_to_me_server.storage.archive import JobArchive
from talk_to_me_server.storage.garbage_collector import GarbageCollector
from talk_to_me_server.tts.piper_engine import PiperEngine
from talk_to_me_server.tts.pool import ProcessSynthesisPool
from talk_to_me_server.tts.scheduler import SynthesisScheduler
from talk_to_me_server.tts.text_segmenter import PiperTextSegmenter
from talk_to_me_server.voices.catalog import VoiceCatalog
from talk_to_me_server.voices.deleter import VoiceDeleter
from talk_to_me_server.voices.downloader import VoiceDownloader
from talk_to_me_server.voices.importer import VoiceImporter
from talk_to_me_server.voices.licenses import VoiceLicensePolicy
from talk_to_me_server.voices.models import VoiceStatus


LOGGER = logging.getLogger("talk_to_me_server")


@dataclass
class Runtime:
    settings: SettingsService
    startup_settings: Settings
    management_access: ManagementAccessPolicy = field(default_factory=ManagementAccessPolicy)
    queue: Any | None = None
    archive: Any | None = None
    scheduler: Any | None = None
    playback: Any | None = None
    text_segmenter: Any | None = None
    process_pool: Any | None = None
    garbage_collector: Any | None = None
    voice_catalog: Any | None = None
    voice_deleter: Any | None = None
    voice_downloader: Any | None = None
    voice_importer: Any | None = None
    global_hotkey: Any | None = None
    http_clients: list[httpx.AsyncClient] = field(default_factory=list)
    _tasks: list[asyncio.Task[Any]] = field(default_factory=list, init=False, repr=False)
    _event_loop: asyncio.AbstractEventLoop | None = field(default=None, init=False, repr=False)
    _hotkey_stop_task: asyncio.Task[Any] | None = field(default=None, init=False, repr=False)
    _playback_stop_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.startup_settings = self.startup_settings.model_copy(deep=True)

    def effective_settings(self) -> Settings:
        desired = self.settings.current()
        startup = self.startup_settings
        general = startup.general.model_copy(update={"theme": desired.general.theme})
        return startup.model_copy(update={"voice": desired.voice, "general": general})

    def live_snapshot(self) -> QueueSettingsSnapshot:
        settings = self.effective_settings()
        return QueueSettingsSnapshot(
            engine=settings.voice.tts,
            speaker=settings.voice.speaker,
            volume=settings.voice.volume,
            workers=settings.general.workers,
        )

    @staticmethod
    def job_error(code: int, message: str, component: str) -> JobError:
        return JobError(code=code, message=message, component=component)

    async def start(self) -> None:
        self._event_loop = asyncio.get_running_loop()
        if self.process_pool is not None:
            await self.process_pool.start()
        if self.scheduler is not None:
            self._tasks.append(asyncio.create_task(self.scheduler.run()))
        if self.playback is not None:
            self._tasks.append(asyncio.create_task(self.playback.run()))
        if self.garbage_collector is not None:
            self._tasks.append(asyncio.create_task(self.garbage_collector.run()))
        if self.global_hotkey is not None:
            try:
                self.global_hotkey.start(self._request_stop_from_hotkey)
                LOGGER.info(
                    "Global stop hotkey registered",
                    extra={"component": "hotkey", "event": "hotkey.started"},
                )
            except Exception:
                LOGGER.warning(
                    "Global stop hotkey is unavailable",
                    exc_info=True,
                    extra={"component": "hotkey", "event": "hotkey.unavailable"},
                )
        LOGGER.info(
            "Runtime started", extra={"component": "runtime", "event": "runtime.started"}
        )

    async def stop(self) -> None:
        self._event_loop = None
        if self.global_hotkey is not None:
            try:
                self.global_hotkey.stop()
            except Exception:
                LOGGER.warning(
                    "Global stop hotkey shutdown failed",
                    exc_info=True,
                    extra={"component": "hotkey", "event": "hotkey.shutdown_failed"},
                )
        if self._hotkey_stop_task is not None and not self._hotkey_stop_task.done():
            self._hotkey_stop_task.cancel()
            await asyncio.gather(self._hotkey_stop_task, return_exceptions=True)
        self._hotkey_stop_task = None
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self.process_pool is not None:
            await self.process_pool.close()
        close_player = getattr(getattr(self.playback, "player", None), "close", None)
        if close_player is not None:
            result = close_player()
            if asyncio.iscoroutine(result):
                await result
        for client in self.http_clients:
            await client.aclose()
        LOGGER.info(
            "Runtime stopped", extra={"component": "runtime", "event": "runtime.stopped"}
        )

    async def stop_playback(self) -> int:
        if self.queue is None or self.archive is None or self.playback is None:
            raise RuntimeError("Text-to-speech runtime is unavailable")
        async with self._playback_stop_lock:
            cancelled = await self.queue.begin_stop()
            try:
                await self.playback.stop()
                for job in cancelled:
                    self.archive.finalize(job)
                for job in cancelled:
                    if not (
                        job.request.calculate_stats
                        or job.request.wait_until_playback_finished
                    ):
                        await self.queue.release(job.id)
                return len(cancelled)
            finally:
                await self.queue.finish_stop()

    def _request_stop_from_hotkey(self) -> None:
        loop = self._event_loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._start_hotkey_stop)
        except RuntimeError:
            LOGGER.warning(
                "Global stop hotkey could not reach the runtime event loop",
                exc_info=True,
                extra={"component": "hotkey", "event": "hotkey.dispatch_failed"},
            )

    def _start_hotkey_stop(self) -> None:
        if self._hotkey_stop_task is not None and not self._hotkey_stop_task.done():
            return
        self._hotkey_stop_task = asyncio.create_task(self._run_hotkey_stop())

    async def _run_hotkey_stop(self) -> None:
        try:
            cancelled = await self.stop_playback()
            LOGGER.info(
                "Playback stopped by global hotkey",
                extra={
                    "component": "hotkey",
                    "event": "hotkey.stop_completed",
                    "cancelled_jobs": cancelled,
                },
            )
        except Exception:
            LOGGER.exception(
                "Global stop hotkey action failed",
                extra={"component": "hotkey", "event": "hotkey.stop_failed"},
            )


def build_runtime(project_root: Path) -> Runtime:
    configure_logging(project_root / "data" / "logs")
    bootstrapped = bootstrap(project_root)
    defaults = Settings.model_validate_json(
        (project_root / "master-data" / "setup.json").read_text(encoding="utf-8")
    )
    service = SettingsService(bootstrapped.setup_path, defaults)
    service.initialize()
    settings = service.current()
    speech_root = _project_path(
        project_root, settings.general.directories.speech_directory
    )
    archive = JobArchive(speech_root)
    queue = QueueManager(
        settings.limits.max_queued_jobs,
        JobIdGenerator(archive.root),
    )
    policy = VoiceLicensePolicy.from_file(
        project_root / "master-data" / "voice-license-policy.json"
    )
    official_root = project_root / "data" / "voices" / "official"
    custom_root = project_root / "data" / "voices" / "custom"
    catalog = VoiceCatalog(
        bootstrapped.catalog_path,
        official_root,
        custom_root,
        policy,
    )

    def resolve_voice(voice_id: str) -> tuple[Path, Path]:
        voice = catalog.get(voice_id)
        if (
            voice is None
            or voice.status is not VoiceStatus.READY
            or voice.model_path is None
            or voice.config_path is None
            or not voice.model_path.is_file()
            or not voice.config_path.is_file()
        ):
            raise FileNotFoundError(f"Voice is not installed: {voice_id}")
        return voice.model_path, voice.config_path

    process_pool = ProcessSynthesisPool(settings.general.workers, resolve_voice)
    text_segmenter = PiperTextSegmenter(
        lambda voice_id: resolve_voice(voice_id)[1]
    )
    scheduler = SynthesisScheduler(
        queue,
        archive,
        process_pool,
        sound_directory=project_root / "master-data" / "sounds",
    )
    player = WindowsAudioPlayer(sounddevice)
    playback = PlaybackCoordinator(queue, archive, player)
    garbage_collector = GarbageCollector(
        archive.root,
        settings.general.directories.garbage_collector_timeout,
        active_ids=lambda: set(queue.active_ids()),
    )
    http_client = httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(60, read=300),
        max_redirects=5,
    )

    async def validate_voice(model_path: Path, config_path: Path) -> None:
        await asyncio.to_thread(PiperEngine.load, model_path, config_path)

    return Runtime(
        settings=service,
        startup_settings=settings,
        queue=queue,
        archive=archive,
        scheduler=scheduler,
        playback=playback,
        text_segmenter=text_segmenter,
        process_pool=process_pool,
        garbage_collector=garbage_collector,
        voice_catalog=catalog,
        voice_deleter=VoiceDeleter(catalog, official_root, custom_root),
        voice_downloader=VoiceDownloader(
            catalog, official_root, http_client, validate_voice
        ),
        voice_importer=VoiceImporter(custom_root, validate_voice),
        global_hotkey=GlobalStopHotkey(),
        http_clients=[http_client],
    )


def _project_path(project_root: Path, configured: Path) -> Path:
    return configured.resolve() if configured.is_absolute() else (project_root / configured).resolve()
