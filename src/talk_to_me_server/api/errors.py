from __future__ import annotations

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from talk_to_me_server.api.envelopes import envelope


def validation_error_response(error: RequestValidationError) -> JSONResponse:
    errors = error.errors()
    status = 413 if any(item.get("type") == "text_limit_exceeded" for item in errors) else 400
    reason = "Request text limit exceeded" if status == 413 else "Invalid request"
    validation_errors = [
        {
            "location": list(item.get("loc", ())),
            "message": item.get("msg", "Invalid value"),
            "type": item.get("type", "value_error"),
        }
        for item in errors
    ]
    return envelope(status, reason, validationErrors=validation_errors)
