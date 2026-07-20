from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from talk_to_me_server.api.envelopes import envelope
from talk_to_me_server.config.models import Settings, StrictModel


router = APIRouter(prefix="/api/v1")


class EmptyRequest(StrictModel):
    pass


class SetSetupRequest(StrictModel):
    setup: Settings


@router.post("/getSetup")
async def get_setup(
    request: Request, _payload: EmptyRequest | None = Body(default=None)
) -> JSONResponse:
    runtime = request.app.state.runtime
    runtime.management_access.authorize(request.client.host, runtime.effective_settings())
    setup = runtime.settings.current().model_dump(mode="json", by_alias=True)
    return envelope(200, "OK", setup=setup)


@router.post("/setSetup")
async def set_setup(request: Request, payload: SetSetupRequest) -> JSONResponse:
    runtime = request.app.state.runtime
    runtime.management_access.authorize(request.client.host, runtime.effective_settings())
    result = runtime.settings.save(payload.setup)
    logger = logging.getLogger("talk_to_me_server")
    logger.info(
        "Configuration changed",
        extra={"component": "configuration", "event": "configuration.changed"},
    )
    if result.restart_fields:
        logger.info(
            "Configuration contains restart-required fields",
            extra={
                "component": "configuration",
                "event": "configuration.restart_required",
            },
        )
    return envelope(
        200,
        "OK",
        setup=result.settings.model_dump(mode="json", by_alias=True),
        restartRequired=bool(result.restart_fields),
        restartFields=list(result.restart_fields),
    )
