from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request
from talk_to_me_server.api.envelopes import envelope
from talk_to_me_server.api.setup_routes import EmptyRequest
from talk_to_me_server.config.models import StrictModel
from talk_to_me_server.voices.deleter import VoiceNotInstalled
from talk_to_me_server.voices.downloader import (
    LicenseRestricted,
    VoiceConflict,
    VoiceDownloadError,
    VoiceNotFound,
    VoiceUnavailable,
)
from talk_to_me_server.voices.importer import RightsConfirmationRequired, VoiceImportError
from talk_to_me_server.voices.models import VoiceDescriptor


router = APIRouter(prefix="/api/v1")


class DownloadVoiceRequest(StrictModel):
    voice_id: str
    license_confirmed: bool = False


class DeleteVoiceRequest(StrictModel):
    voice_id: str


@router.post("/getVoices")
async def get_voices(
    request: Request, _payload: EmptyRequest | None = Body(default=None)
):
    runtime = request.app.state.runtime
    runtime.management_access.authorize(request.client.host, runtime.effective_settings())
    if runtime.voice_catalog is None:
        return envelope(503, "Voice catalog is unavailable")
    voices = [_voice_payload(voice) for voice in runtime.voice_catalog.list()]
    return envelope(200, "OK", voices=voices)


@router.post("/downloadVoice")
async def download_voice(request: Request, payload: DownloadVoiceRequest):
    runtime = request.app.state.runtime
    runtime.management_access.authorize(request.client.host, runtime.effective_settings())
    if runtime.voice_downloader is None:
        return envelope(503, "Voice downloader is unavailable")
    try:
        voice = await runtime.voice_downloader.download(
            payload.voice_id, license_confirmed=payload.license_confirmed
        )
    except VoiceNotFound as error:
        return envelope(404, str(error))
    except LicenseRestricted as error:
        return envelope(403, str(error))
    except VoiceConflict as error:
        return envelope(409, str(error))
    except VoiceUnavailable as error:
        return envelope(502, str(error))
    except VoiceDownloadError as error:
        return envelope(502, str(error))
    return envelope(200, "OK", voice=_voice_payload(voice))


@router.post("/deleteVoice")
async def delete_voice(request: Request, payload: DeleteVoiceRequest):
    runtime = request.app.state.runtime
    runtime.management_access.authorize(request.client.host, runtime.effective_settings())
    if runtime.voice_deleter is None:
        return envelope(503, "Voice deleter is unavailable")
    try:
        runtime.voice_deleter.delete(payload.voice_id)
    except VoiceNotInstalled as error:
        return envelope(404, str(error))
    return envelope(200, "OK", deletedVoiceId=payload.voice_id)


@router.post("/importVoice")
async def import_voice(request: Request):
    runtime = request.app.state.runtime
    runtime.management_access.authorize(request.client.host, runtime.effective_settings())
    if runtime.voice_importer is None:
        return envelope(503, "Voice importer is unavailable")
    if not _is_multipart_content_type(request.headers.get("content-type", "")):
        return envelope(415, "Only multipart local voice import is supported")
    try:
        voice = await _import_multipart(request, runtime.voice_importer)
    except (RightsConfirmationRequired, VoiceImportError, ValueError) as error:
        return envelope(400, str(error))
    except VoiceConflict as error:
        return envelope(409, str(error))
    except VoiceDownloadError as error:
        return envelope(502, str(error))
    return envelope(200, "OK", voice=_voice_payload(voice))


def _voice_payload(voice: VoiceDescriptor) -> dict[str, Any]:
    payload = voice.model_dump(mode="json", by_alias=True)
    if voice.model_path is not None:
        payload["modelPath"] = str(voice.model_path.resolve())
    if voice.config_path is not None:
        payload["configPath"] = str(voice.config_path.resolve())
    return payload


def _is_multipart_content_type(value: str) -> bool:
    return value.partition(";")[0].strip().casefold() == "multipart/form-data"


async def _import_multipart(request: Request, importer: Any):
    form = await request.form()
    model = form.get("model")
    config = form.get("config")
    if not hasattr(model, "read") or not hasattr(config, "read"):
        raise VoiceImportError("Multipart upload requires model and config files")
    rights_confirmed = str(form.get("rightsConfirmed", "")).casefold() == "true"
    return importer.import_bytes(
        await model.read(),
        await config.read(),
        display_name=str(form.get("displayName", "")),
        license_name=str(form.get("license", "")),
        rights_confirmed=rights_confirmed,
    )
