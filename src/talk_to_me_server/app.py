from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from talk_to_me_server.api.access import ManagementAccessDenied
from talk_to_me_server.api.envelopes import envelope
from talk_to_me_server.api.errors import validation_error_response
from talk_to_me_server.api.setup_routes import router as setup_router
from talk_to_me_server.api.tts_routes import router as tts_router
from talk_to_me_server.api.voice_routes import router as voice_router
from talk_to_me_server.lifespan import Runtime, build_runtime


PORTAL_LOCALES = {
    "ar", "bg", "cs", "da", "de", "el", "en", "es", "et", "fi", "fr", "ga", "hr",
    "hu", "it", "ja", "lt", "lv", "mt", "nl", "no", "pl", "pt", "ro", "ru", "sk",
    "sl", "sv", "uk", "zh-Hans",
}


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, limit_provider: Callable[[Scope], int]) -> None:
        self.app = app
        self.limit_provider = limit_provider

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return
        limit = self.limit_provider(scope)
        content_length = _content_length(scope)
        if content_length is not None and content_length > limit:
            await envelope(413, "Request body is too large")(scope, receive, send)
            return
        chunks: list[bytes] = []
        total = 0
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > limit:
                await envelope(413, "Request body is too large")(scope, receive, send)
                return
            chunks.append(chunk)
            more_body = message.get("more_body", False)
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if replayed:
                return {"type": "http.request", "body": b"", "more_body": False}
            replayed = True
            return {"type": "http.request", "body": b"".join(chunks), "more_body": False}

        await self.app(scope, replay, send)


class PortalAccessMiddleware:
    """Keep the management portal and its assets on loopback by default."""

    def __init__(self, app: ASGIApp, runtime: Runtime) -> None:
        self.app = app
        self.runtime = runtime

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not scope.get("path", "").startswith("/api/"):
            client = scope.get("client")
            client_ip = client[0] if client else ""
            try:
                self.runtime.management_access.authorize(
                    client_ip, self.runtime.effective_settings()
                )
            except ManagementAccessDenied as error:
                await envelope(403, str(error))(scope, receive, send)
                return
        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def add_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append(
                    (
                        b"content-security-policy",
                        b"default-src 'self'; script-src 'self'; style-src 'self'; "
                        b"img-src 'self' data:; connect-src 'self'; object-src 'none'",
                    )
                )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, add_headers)


class CorrelationIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        correlation_id = uuid4().hex
        scope.setdefault("state", {})["correlation_id"] = correlation_id

        async def add_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-correlation-id", correlation_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, add_header)


def create_app(runtime: Runtime | None = None) -> FastAPI:
    project_root = Path(__file__).resolve().parents[2]
    selected_runtime = runtime or build_runtime(project_root)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await selected_runtime.start()
        try:
            yield
        finally:
            await selected_runtime.stop()

    app = FastAPI(lifespan=lifespan)
    app.state.runtime = selected_runtime
    app.include_router(setup_router)
    app.include_router(tts_router)
    app.include_router(voice_router)
    app.add_middleware(
        BodyLimitMiddleware,
        limit_provider=lambda _scope: selected_runtime.effective_settings().limits.max_request_body_bytes,
    )
    app.add_middleware(PortalAccessMiddleware, runtime=selected_runtime)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        _request: Request, error: RequestValidationError
    ) -> Any:
        return validation_error_response(error)

    @app.exception_handler(ManagementAccessDenied)
    async def access_handler(_request: Request, error: ManagementAccessDenied) -> Any:
        return envelope(403, str(error))

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(_request: Request, error: StarletteHTTPException) -> Any:
        reason = "Method not allowed" if error.status_code == 405 else "Not found"
        return envelope(error.status_code, reason)

    @app.exception_handler(Exception)
    async def unexpected_handler(request: Request, error: Exception) -> Any:
        correlation_id = getattr(request.state, "correlation_id", uuid4().hex)
        logging.getLogger("talk_to_me_server").exception(
            "Unhandled API exception",
            exc_info=error,
            extra={
                "component": "api",
                "event": "api.unhandled_exception",
                "correlation_id": correlation_id,
            },
        )
        response = envelope(
            500,
            "Internal server error",
            correlationId=correlation_id,
        )
        response.headers["x-correlation-id"] = correlation_id
        return response

    @app.get("/master-data/request.json", include_in_schema=False)
    async def master_request() -> FileResponse:
        return FileResponse(project_root / "master-data" / "request.json")

    @app.get("/master-data/benchmark-request.json", include_in_schema=False)
    async def benchmark_request() -> FileResponse:
        return FileResponse(project_root / "master-data" / "benchmark-request.json")

    @app.get("/master-data/i18n/{locale}.json", include_in_schema=False)
    async def portal_locale(locale: str) -> FileResponse:
        if locale not in PORTAL_LOCALES:
            raise StarletteHTTPException(status_code=404)
        return FileResponse(project_root / "master-data" / "i18n" / f"{locale}.json")

    @app.api_route(
        "/api/{_path:path}",
        methods=["GET", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        include_in_schema=False,
    )
    async def reject_non_post_api(_path: str) -> Any:
        return envelope(405, "Method not allowed")

    app.mount("/", StaticFiles(directory=project_root / "web", html=True), name="portal")

    return app


def _content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name.lower() == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None
