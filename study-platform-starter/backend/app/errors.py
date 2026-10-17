"""Normalized JSON error responses.

Every error response has the shape::

    {"error": {"type": str, "message": str, "request_id": str, ...}}

Internal exception details are never leaked to clients in production.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging_config import get_request_id

logger = logging.getLogger("app.error")


def _error_payload(
    request_id: str,
    error_type: str,
    message: str,
    **extra: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": error_type,
        "message": message,
        "request_id": request_id,
    }
    payload.update(extra)
    return {"error": payload}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = get_request_id()
        return JSONResponse(
            status_code=422,
            content=_error_payload(
                request_id,
                "validation_error",
                "Request validation failed.",
                details=_sanitize_validation_errors(exc.errors()),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = get_request_id()
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(request_id, "http_error", str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
        request_id = get_request_id()
        logger.exception("unhandled_exception", extra={"request_id": request_id})
        return JSONResponse(
            status_code=500,
            content=_error_payload(
                request_id,
                "internal_error",
                "An unexpected error occurred.",
            ),
        )


def _sanitize_validation_errors(errors: list[dict[str, object]]) -> list[dict[str, object]]:
    safe: list[dict[str, object]] = []
    for error in errors:
        safe.append(
            {
                "loc": [str(part) for part in error.get("loc", [])],
                "msg": str(error.get("msg", "")),
                "type": str(error.get("type", "")),
            }
        )
    return safe


__all__ = ["register_exception_handlers"]
