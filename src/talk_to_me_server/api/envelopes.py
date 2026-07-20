from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def envelope(status: int, reason: str, **payload: Any) -> JSONResponse:
    content = {
        "version": 1,
        "reasonCode": status,
        "reasonText": reason,
        **payload,
    }
    return JSONResponse(status_code=status, content=content)
