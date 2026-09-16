from decimal import Decimal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.middleware_trace import trace_id_var
from app.schemas.common import ErrorBody, ErrorEnvelope


def _sanitize_item(obj: object) -> object:
    """Recursively replace non-JSON-serialisable values with their string representation.

    Pydantic ``field_validator`` errors place the raw exception in ``ctx["error"]``, and a
    constraint on a ``Decimal`` field echoes a ``Decimal`` into ``ctx``; ``json`` refuses both.
    The ``isinstance(Exception)`` guard runs first so it applies at any nesting depth.
    """
    if isinstance(obj, Exception | Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_item(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_item(item) for item in obj]
    return obj


def _sanitize_errors(errors: list[object]) -> list[object]:
    return [_sanitize_item(e) for e in errors]


def _envelope(code: str, message: str, details: list[object], status: int) -> JSONResponse:
    body = ErrorEnvelope(
        error=ErrorBody(code=code, message=message, details=details),
        trace_id=trace_id_var.get() or None,
    )
    return JSONResponse(status_code=status, content=body.model_dump())


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        # Structured detail (dict/list): carry it in ``details[]`` so JSON clients can read
        # it, rather than flattening it to a Python-repr string in ``message``. String details
        # keep their existing behaviour (message = the string).
        if isinstance(detail, dict):
            message = str(detail.get("error", "error"))
            return _envelope("HTTP_ERROR", message, [_sanitize_item(detail)], exc.status_code)
        if isinstance(detail, list):
            return _envelope("HTTP_ERROR", "error", _sanitize_errors(list(detail)), exc.status_code)
        return _envelope("HTTP_ERROR", str(detail), [], exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _envelope("VALIDATION_ERROR", "Invalid request", _sanitize_errors(list(exc.errors())), 422)
