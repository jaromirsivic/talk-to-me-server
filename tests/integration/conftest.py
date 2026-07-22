from io import BytesIO
import wave

import pytest
from starlette.testclient import TestClient

from talk_to_me_server.app import create_app
from talk_to_me_server.config.models import Settings
from talk_to_me_server.config.service import SettingsService
from talk_to_me_server.domain.ids import JobIdGenerator
from talk_to_me_server.domain.queue import QueueManager
from talk_to_me_server.lifespan import Runtime
from talk_to_me_server.playback.base import PlaybackValue
from talk_to_me_server.playback.coordinator import PlaybackCoordinator
from talk_to_me_server.storage.archive import JobArchive
from talk_to_me_server.tts.base import SynthesisCommand, SynthesisResult
from talk_to_me_server.tts.scheduler import SynthesisScheduler
from talk_to_me_server.tts.text_segmenter import split_text


class FakeSynthesisPool:
    async def synthesize(self, command: SynthesisCommand) -> SynthesisResult:
        command.output_path.parent.mkdir(parents=True, exist_ok=True)
        command.output_path.write_bytes(command.text.encode("utf-8"))
        return SynthesisResult(command.job_id, command.index, command.output_path, process_id=1)


class FakeAudioPlayer:
    def __init__(self) -> None:
        self.played: list[str] = []
        self.received_indices: list[int] = []

    async def play(self, values, volume: int, on_started, on_finished) -> None:
        async for value in values:
            assert isinstance(value, PlaybackValue)
            self.received_indices.append(value.index)
            await on_started(value.index)
            data = value.path.read_bytes()
            try:
                with wave.open(BytesIO(data), "rb") as wav_file:
                    frames = wav_file.getnframes()
                    audio = wav_file.readframes(frames)
                    if audio and set(audio) <= {0}:
                        duration_ms = round(frames * 1_000 / wav_file.getframerate())
                        self.played.append(f"pause:{duration_ms}ms")
                    elif audio:
                        marker = int.from_bytes(audio[:2], "little", signed=True)
                        self.played.append(f"sound:{marker}")
            except (EOFError, wave.Error):
                self.played.append(data.decode("utf-8"))
            await on_finished(value.index)

    async def stop(self) -> None:
        return None


class FakeTextSegmenter:
    async def split(self, text: str, _speaker: str) -> list[str]:
        return split_text(
            text,
            phoneme_type="espeak",
            espeak_voice="en-us",
        )


@pytest.fixture
def tts_runtime(tmp_path, approved_settings: Settings):
    service = SettingsService(tmp_path / "setup.json", approved_settings)
    service.initialize()
    archive = JobArchive(tmp_path / "archive")
    queue = QueueManager(100, JobIdGenerator(archive.root))
    pool = FakeSynthesisPool()
    player = FakeAudioPlayer()
    sound_directory = tmp_path / "sounds"
    sound_directory.mkdir()
    for marker, name in enumerate(
        ("positive_gong.wav", "neutral_gong.wav", "negative_gong.wav"), start=1
    ):
        output = BytesIO()
        with wave.open(output, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22_050)
            wav_file.writeframes(marker.to_bytes(2, "little", signed=True))
        (sound_directory / name).write_bytes(output.getvalue())
    scheduler = SynthesisScheduler(
        queue, archive, pool, sound_directory=sound_directory
    )
    playback = PlaybackCoordinator(queue, archive, player)
    return Runtime(
        settings=service,
        startup_settings=service.current(),
        queue=queue,
        archive=archive,
        scheduler=scheduler,
        playback=playback,
        text_segmenter=FakeTextSegmenter(),
    )


@pytest.fixture
def tts_client(tts_runtime):
    with TestClient(create_app(tts_runtime), client=("127.0.0.1", 50_000)) as client:
        yield client
