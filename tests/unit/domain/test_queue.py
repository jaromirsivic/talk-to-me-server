import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from talk_to_me_server.api.schemas import TextToSpeechRequest
from talk_to_me_server.domain.ids import JobIdGenerator
from talk_to_me_server.domain.jobs import JobError, JobState, ValueState
from talk_to_me_server.domain.queue import QueueManager, QueueSettingsSnapshot


NOW = datetime(2026, 7, 18, 12, 0, tzinfo=timezone(timedelta(hours=2)))


def snapshot() -> QueueSettingsSnapshot:
    return QueueSettingsSnapshot(
        engine="Piper",
        speaker="en_US-ljspeech-medium",
        volume=100,
        workers=4,
    )


@pytest.fixture
def queue(tmp_path) -> QueueManager:
    ticks = iter(range(1_000))
    return QueueManager(
        max_jobs=2,
        id_generator=JobIdGenerator(tmp_path),
        wall_clock=lambda: NOW,
        monotonic_clock=lambda: next(ticks),
    )


@pytest.mark.asyncio
async def test_low_is_admitted_only_when_no_active_job(queue) -> None:
    first = await queue.enqueue(
        TextToSpeechRequest(values=["optional"], importance="low"), snapshot()
    )
    second = await queue.enqueue(
        TextToSpeechRequest(values=["optional"], importance="low"), snapshot()
    )

    assert first.accepted and first.job is not None
    assert not second.accepted
    assert second.job is None
    assert queue.active_count == 1
    assert second.status == 200
    assert second.reason == (
        "Message not processed. Queue is not empty and in that case low importance messages are "
        "not processed."
    )


@pytest.mark.asyncio
async def test_high_is_always_admitted_until_queue_is_full(queue) -> None:
    assert (await queue.enqueue(TextToSpeechRequest(values=["a"]), snapshot())).accepted
    assert (
        await queue.enqueue(
            TextToSpeechRequest(values=["b"], importance="high"), snapshot()
        )
    ).accepted
    full = await queue.enqueue(TextToSpeechRequest(values=["c"]), snapshot())
    assert full.status == 429
    assert full.reason == "Queue is full"


@pytest.mark.asyncio
async def test_terminal_job_held_for_waiter_is_not_active_for_low_or_capacity(queue) -> None:
    first = (await queue.enqueue(TextToSpeechRequest(values=["a"]), snapshot())).job
    assert first is not None
    await queue.fail(first.id, JobError(code=500, message="failed"))

    optional = await queue.enqueue(
        TextToSpeechRequest(values=["optional"], importance="low"), snapshot()
    )

    assert optional.accepted is True
    assert first.id not in queue.active_ids()


@pytest.mark.asyncio
async def test_active_snapshot_excludes_terminal_jobs_and_includes_worker_details(queue) -> None:
    terminal = (await queue.enqueue(TextToSpeechRequest(values=["done"]), snapshot())).job
    active = (
        await queue.enqueue(TextToSpeechRequest(values=["first", "second"]), snapshot())
    ).job
    assert terminal is not None and active is not None
    await queue.fail(terminal.id, JobError(code=500, message="failed"))
    await queue.claim_for_synthesis(wait=False)
    await queue.mark_value_processing(active.id, 0)
    await queue.record_value_worker_index(active.id, 0, 2)

    jobs = await queue.active_snapshot()

    assert [job["id"] for job in jobs] == [active.id]
    assert jobs[0]["state"] == "processing"
    assert jobs[0]["values"][0]["workerIndex"] == 2
    assert jobs[0]["values"][0]["totalWorkers"] == 4


@pytest.mark.asyncio
async def test_volume_multiplier_is_clamped_and_applied_to_snapshot(queue) -> None:
    low = await queue.enqueue(
        TextToSpeechRequest(values=["quiet"], volume_multiplier=-0.5), snapshot()
    )
    await queue.fail(low.job.id, None)
    high = await queue.enqueue(
        TextToSpeechRequest(values=["loud"], volume_multiplier=1.5), snapshot()
    )

    assert low.job.snapshot.volume == 0
    assert high.job.snapshot.volume == 100


@pytest.mark.asyncio
async def test_volume_multiplier_rounds_the_chosen_setup_volume(queue) -> None:
    admission = await queue.enqueue(
        TextToSpeechRequest(values=["scaled"], volume_multiplier=0.505), snapshot()
    )

    assert admission.job.snapshot.volume == 51


@pytest.mark.asyncio
async def test_synthesis_and_playback_claims_preserve_global_fifo(queue) -> None:
    a = (await queue.enqueue(TextToSpeechRequest(values=["a"]), snapshot())).job
    b = (await queue.enqueue(TextToSpeechRequest(values=["b"]), snapshot())).job
    assert a is not None and b is not None

    assert (await queue.claim_for_synthesis(wait=False)).id == a.id
    assert await queue.claim_for_synthesis(wait=False) is None
    await queue.mark_value_processing(a.id, 0)
    await queue.mark_value_processed(a.id, 0)

    assert (await queue.claim_for_playback(wait=False)).id == a.id
    assert a.state is JobState.PLAYING
    assert await queue.claim_for_synthesis(wait=False) is None

    await queue.mark_synthesis_finished(a.id)
    assert (await queue.claim_for_synthesis(wait=False)).id == b.id
    await queue.mark_value_processing(b.id, 0)
    await queue.mark_value_processed(b.id, 0)
    await queue.mark_synthesis_finished(b.id)

    assert await queue.claim_for_playback(wait=False) is None
    await queue.finish(a.id)
    assert (await queue.claim_for_playback(wait=False)).id == b.id


@pytest.mark.asyncio
async def test_wait_for_value_returns_as_soon_as_that_value_is_processed(queue) -> None:
    job = (await queue.enqueue(TextToSpeechRequest(values=["a", "b"]), snapshot())).job
    assert job is not None
    await queue.claim_for_synthesis(wait=False)
    waiter = asyncio.create_task(queue.wait_for_value(job.id, 0))
    await asyncio.sleep(0)

    await queue.mark_value_processing(job.id, 0)
    await queue.mark_value_processed(job.id, 0)

    value = await asyncio.wait_for(waiter, timeout=0.5)
    assert value.index == 0
    assert value.state is ValueState.PROCESSED


@pytest.mark.asyncio
async def test_wait_terminal_is_notified_and_release_removes_job(queue) -> None:
    job = (await queue.enqueue(TextToSpeechRequest(values=["a"]), snapshot())).job
    assert job is not None
    waiter = asyncio.create_task(queue.wait_terminal(job.id))
    await asyncio.sleep(0)

    await queue.fail(job.id, JobError(code=503, message="worker unavailable"))
    terminal = await asyncio.wait_for(waiter, timeout=0.5)
    assert terminal.state is JobState.FAILED

    await queue.release(job.id)
    assert queue.get(job.id) is None


@pytest.mark.asyncio
async def test_cancel_all_atomically_cancels_active_jobs_and_wakes_waiters(queue) -> None:
    first = (await queue.enqueue(TextToSpeechRequest(values=["a"]), snapshot())).job
    second = (await queue.enqueue(TextToSpeechRequest(values=["b"]), snapshot())).job
    assert first is not None and second is not None
    await queue.claim_for_synthesis(wait=False)
    waiter = asyncio.create_task(queue.wait_terminal(first.id))
    await asyncio.sleep(0)

    cancelled = await queue.cancel_all()
    terminal = await asyncio.wait_for(waiter, timeout=0.5)

    assert {job.id for job in cancelled} == {first.id, second.id}
    assert terminal.state is JobState.CANCELLED
    assert terminal.errors[0].code == 409
    assert terminal.errors[0].message == "Stopped by request"
    assert all(value.state is ValueState.CANCELLED for job in cancelled for value in job.values)
    assert queue.active_count == 0
    assert await queue.claim_for_synthesis(wait=False) is None
    assert await queue.claim_for_playback(wait=False) is None


@pytest.mark.asyncio
async def test_begin_stop_blocks_new_admission_until_stop_finishes(queue) -> None:
    await queue.begin_stop()
    admission = asyncio.create_task(
        queue.enqueue(TextToSpeechRequest(values=["after"]), snapshot())
    )
    await asyncio.sleep(0)

    assert not admission.done()

    await queue.finish_stop()
    result = await asyncio.wait_for(admission, timeout=0.5)
    assert result.accepted
