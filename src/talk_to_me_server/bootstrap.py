from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from talk_to_me_server.config.models import Settings
from talk_to_me_server.config.service import load_settings
from talk_to_me_server.storage.atomic import atomic_write_json
from talk_to_me_server.tts.piper_engine import PiperEngine
from talk_to_me_server.voices.catalog import VoiceCatalog
from talk_to_me_server.voices.downloader import VoiceDownloader
from talk_to_me_server.voices.licenses import VoiceLicensePolicy


DEFAULT_VOICE = "en_US-ljspeech-medium"


@dataclass(frozen=True)
class BootstrapResult:
    created: bool
    data_root: Path
    setup_path: Path
    catalog_path: Path
    default_voice_path: Path | None = None


def bootstrap(project_root: Path, *, download_default_voice: bool = False) -> BootstrapResult:
    project_root = project_root.resolve()
    source_root = Path(__file__).resolve().parents[2]
    master_root = project_root / "master-data"
    source_master = master_root if master_root.is_dir() else source_root / "master-data"
    data_root = project_root / "data"
    for relative in (
        "temp",
        "speech",
        "text",
        "logs",
        "voices/official",
        "voices/custom",
        "catalog",
    ):
        (data_root / relative).mkdir(parents=True, exist_ok=True)

    setup_path = data_root / "setup.json"
    created = not setup_path.exists()
    if created:
        settings = Settings.model_validate_json(
            (source_master / "setup.json").read_text(encoding="utf-8")
        )
        atomic_write_json(setup_path, settings)
    else:
        load_settings(setup_path, migrate_legacy_severity=True)

    catalog_path = data_root / "catalog" / "official-voices.json"
    if not catalog_path.exists():
        shutil.copyfile(source_master / "official-voices.json", catalog_path)
    _validate_catalog(catalog_path)

    voice_path = None
    if download_default_voice:
        voice_path = asyncio.run(
            _download_default(project_root, source_master, data_root, catalog_path)
        )
    _record_state(data_root, setup_path, catalog_path, voice_path)
    return BootstrapResult(
        created=created,
        data_root=data_root,
        setup_path=setup_path,
        catalog_path=catalog_path,
        default_voice_path=voice_path,
    )


async def _download_default(
    project_root: Path,
    master_root: Path,
    data_root: Path,
    catalog_path: Path,
) -> Path:
    manifest = json.loads(
        (master_root / "install-manifest.json").read_text(encoding="utf-8")
    )
    await refresh_official_catalog(
        manifest["officialCatalog"]["url"],
        manifest["officialCatalog"]["baseUrl"],
        catalog_path,
        default_voice=manifest["defaultVoice"],
    )
    policy = VoiceLicensePolicy.from_file(master_root / "voice-license-policy.json")
    catalog = VoiceCatalog(
        catalog_path,
        data_root / "voices" / "official",
        data_root / "voices" / "custom",
        policy,
    )
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(60, read=300),
        max_redirects=5,
    ) as client:
        downloader = VoiceDownloader(
            catalog,
            data_root / "voices" / "official",
            client,
            validator=_validate_voice_pair,
        )
        voice = await downloader.download(DEFAULT_VOICE)
    if voice.model_path is None:
        raise RuntimeError("Default voice was not activated")
    return voice.model_path.parent


async def refresh_official_catalog(
    catalog_url: str,
    base_url: str,
    destination: Path,
    *,
    default_voice: dict[str, Any] | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> None:
    client = http_client or httpx.AsyncClient(follow_redirects=True, timeout=60)
    owned_client = http_client is None
    try:
        response = await client.get(catalog_url)
        response.raise_for_status()
        raw = response.json()
        if not isinstance(raw, dict):
            raise ValueError("Official Piper catalog must be an object")
        normalized = []
        for voice_id, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            files = entry.get("files", {})
            model_path = next((path for path in files if path.endswith(".onnx")), None)
            config_path = next(
                (path for path in files if path.endswith(".onnx.json")), None
            )
            card_path = next((path for path in files if path.endswith("MODEL_CARD")), None)
            if model_path is None or config_path is None:
                continue
            language = entry.get("language") or {}
            record = {
                "id": voice_id,
                "name": entry.get("name") or voice_id,
                "language": language.get("code") or "und",
                "quality": entry.get("quality") or "unknown",
                "sizeBytes": files[model_path].get("size_bytes"),
                "license": None,
                "modelUrl": urljoin(base_url, model_path),
                "configUrl": urljoin(base_url, config_path),
                "modelCardUrl": urljoin(base_url, card_path) if card_path else None,
                "modelMd5": files[model_path].get("md5_digest"),
                "configMd5": files[config_path].get("md5_digest"),
            }
            normalized.append(record)
        await _enrich_licenses(client, normalized)
        if default_voice:
            for record in normalized:
                if record["id"] == default_voice["id"]:
                    record.update(
                        license=default_voice["license"],
                        modelSha256=default_voice["modelSha256"],
                        configSha256=default_voice["configSha256"],
                    )
                    break
        if not normalized:
            raise ValueError("Official Piper catalog contains no usable voices")
        atomic_write_json(destination, {"version": 1, "voices": normalized})
    finally:
        if owned_client:
            await client.aclose()


async def _enrich_licenses(
    client: httpx.AsyncClient, records: list[dict[str, Any]]
) -> None:
    semaphore = asyncio.Semaphore(12)

    async def enrich(record: dict[str, Any]) -> None:
        url = record.get("modelCardUrl")
        if not url:
            return
        try:
            async with semaphore:
                response = await client.get(url)
                response.raise_for_status()
            record["license"] = _model_card_license(response.text)
        except (httpx.HTTPError, UnicodeError):
            record["license"] = None

    await asyncio.gather(*(enrich(record) for record in records))


def _model_card_license(text: str) -> str | None:
    match = re.search(r"(?im)^\s*[-*]?\s*license\s*:\s*(.+?)\s*$", text)
    if match is None:
        return None
    value = match.group(1).strip().strip("*_`")
    normalized = " ".join(value.upper().replace("_", "-").split())
    aliases = {
        "PUBLIC DOMAIN": "Public Domain",
        "PUBLIC-DOMAIN": "Public Domain",
        "CC0": "CC0-1.0",
        "CC 0": "CC0-1.0",
        "CC-BY 4.0": "CC-BY-4.0",
        "CC BY 4.0": "CC-BY-4.0",
    }
    return aliases.get(normalized, value)


def _validate_catalog(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("voices"), list):
        raise ValueError("Invalid normalized voice catalog")


def _validate_voice_pair(model_path: Path, config_path: Path) -> None:
    PiperEngine.load(model_path, config_path)


def _record_state(
    data_root: Path,
    setup_path: Path,
    catalog_path: Path,
    voice_path: Path | None,
) -> None:
    files = [setup_path, catalog_path]
    if voice_path is not None:
        files.extend(path for path in voice_path.iterdir() if path.is_file())
    atomic_write_json(
        data_root / "bootstrap-state.json",
        {"version": 1, "files": {str(path): _sha256(path) for path in files}},
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download-default-voice", action="store_true")
    args = parser.parse_args()
    bootstrap(
        Path(__file__).resolve().parents[2],
        download_default_voice=args.download_default_voice,
    )


if __name__ == "__main__":
    main()
