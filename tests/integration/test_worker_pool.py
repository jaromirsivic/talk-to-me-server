import asyncio
import os
import wave
from pathlib import Path

import pytest

from talk_to_me_server.tts.base import SynthesisCommand
from talk_to_me_server.tts.pool import ProcessSynthesisPool


class EchoEngine:
    def synthesize(self, text: str, output: Path) -> None:
        crash_marker = output.with_suffix(".crashed")
        if text == "crash-once" and not crash_marker.exists():
            crash_marker.write_text("crashed", encoding="utf-8")
            os._exit(17)
        with wave.open(str(output), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22_050)
            wav_file.writeframes((text + str(os.getpid())).encode("utf-8") * 8)


def echo_engine_factory(_model: Path, _config: Path) -> EchoEngine:
    return EchoEngine()


class VoiceResolver:
    def __init__(self, root: Path) -> None:
        self.root = root

    def __call__(self, _speaker: str) -> tuple[Path, Path]:
        return self.root / "voice.onnx", self.root / "voice.onnx.json"


def command(tmp_path: Path, index: int, text: str = "hello") -> SynthesisCommand:
    return SynthesisCommand(
        job_id="job-1",
        index=index,
        text=text,
        speaker="voice",
        output_path=tmp_path / f"{index:03d}.wav",
    )


@pytest.mark.asyncio
async def test_pool_uses_spawned_processes_and_preserves_indices(tmp_path) -> None:
    pool = ProcessSynthesisPool(
        workers=2,
        voice_resolver=VoiceResolver(tmp_path),
        engine_factory=echo_engine_factory,
    )
    await pool.start()
    try:
        results = await asyncio.gather(
            *(pool.synthesize(command(tmp_path, index)) for index in range(8))
        )
    finally:
        await pool.close()

    assert sorted(result.index for result in results) == list(range(8))
    assert all(result.process_id != os.getpid() for result in results)
    assert 1 <= len({result.process_id for result in results}) <= 2
    assert all(0 <= result.worker_index < 2 for result in results)
    worker_by_process = {result.process_id: result.worker_index for result in results}
    assert len(worker_by_process) == len({result.worker_index for result in results})
    assert all(result.output_path.is_file() for result in results)


@pytest.mark.asyncio
async def test_worker_crash_rebuilds_pool_and_retries_once(tmp_path) -> None:
    pool = ProcessSynthesisPool(
        workers=1,
        voice_resolver=VoiceResolver(tmp_path),
        engine_factory=echo_engine_factory,
    )
    await pool.start()
    try:
        result = await pool.synthesize(command(tmp_path, 0, text="crash-once"))
    finally:
        await pool.close()

    assert result.output_path.is_file()


@pytest.mark.parametrize("workers", [0, 17])
def test_worker_bounds_are_enforced(tmp_path, workers) -> None:
    with pytest.raises(ValueError, match="between 1 and 16"):
        ProcessSynthesisPool(
            workers=workers,
            voice_resolver=VoiceResolver(tmp_path),
            engine_factory=echo_engine_factory,
        )
