from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.background import BackgroundTask

from talk_to_me_server.api.envelopes import envelope
from talk_to_me_server.api.schemas import QueueInfoMode, QueueInfoRequest, TextToSpeechRequest
from talk_to_me_server.domain.stats import calculate_stats


router = APIRouter(prefix="/api/v1")


@router.post("/queueInfo")
async def queue_info(
    request: Request, payload: QueueInfoRequest | None = None
) -> JSONResponse:
    runtime = request.app.state.runtime
    if runtime.queue is None:
        return envelope(503, "Text-to-speech runtime is unavailable")
    mode = payload.mode if payload is not None else QueueInfoMode.MAX
    if mode is QueueInfoMode.MIN:
        active_count = await runtime.queue.active_count_snapshot()
        return envelope(
            200,
            "OK",
            hasActiveJobs=active_count > 0,
            activeJobCount=active_count,
        )
    jobs = await runtime.queue.active_snapshot()
    return envelope(
        200,
        "OK",
        hasActiveJobs=bool(jobs),
        activeJobCount=len(jobs),
        jobs=jobs,
    )


@router.post("/stop")
async def stop_playback(request: Request) -> JSONResponse:
    runtime = request.app.state.runtime
    if runtime.queue is None or runtime.archive is None or runtime.playback is None:
        return envelope(503, "Text-to-speech runtime is unavailable")
    cancelled = await runtime.queue.begin_stop()
    try:
        await runtime.playback.stop()
        for job in cancelled:
            runtime.archive.finalize(job)
        for job in cancelled:
            if not (job.request.calculate_stats or job.request.wait_until_playback_finished):
                await runtime.queue.release(job.id)
        return envelope(200, "Playback stopped", cancelledJobs=len(cancelled))
    except OSError:
        return envelope(507, "Archive is not writable")
    finally:
        await runtime.queue.finish_stop()


@router.post("/textToSpeech")
async def text_to_speech(
    request: Request, payload: TextToSpeechRequest
) -> JSONResponse:
    runtime = request.app.state.runtime
    snapshot = None
    if payload.value is not None:
        if runtime.text_segmenter is None:
            return envelope(503, "Text segmentation is unavailable")
        snapshot = runtime.live_snapshot()
        try:
            values = await runtime.text_segmenter.split(
                payload.value, snapshot.speaker
            )
            payload = payload.with_values(values)
        except ValidationError as error:
            raise RequestValidationError(error.errors()) from error
        except (OSError, ValueError, KeyError):
            return envelope(503, "Text segmentation is unavailable")
    if payload.values is None or payload.values == []:
        return envelope(200, "No values to process")
    if runtime.queue is None or runtime.archive is None:
        return envelope(503, "Text-to-speech runtime is unavailable")
    admission = await runtime.queue.enqueue(
        payload, snapshot or runtime.live_snapshot()
    )
    if not admission.accepted or admission.job is None:
        return envelope(admission.status, admission.reason)
    job = admission.job
    try:
        runtime.archive.create(job)
    except OSError:
        await runtime.queue.fail(
            job.id,
            runtime.job_error(507, "Archive is not writable", "archive"),
        )
        await runtime.queue.release(job.id)
        return envelope(507, "Archive is not writable")
    if not (payload.calculate_stats or payload.wait_until_playback_finished):
        return envelope(200, "Accepted", jobId=job.id)
    terminal = await runtime.queue.wait_terminal(job.id)
    status = terminal.errors[0].code if terminal.errors else 200
    reason = terminal.errors[0].message if terminal.errors else "OK"
    response = envelope(status, reason, job=terminal.to_dict())
    if payload.calculate_stats:
        response = envelope(
            status,
            reason,
            job=terminal.to_dict(include_worker_details=True),
            stats=calculate_stats(terminal),
        )
    response.background = BackgroundTask(runtime.queue.release, job.id)
    return response
