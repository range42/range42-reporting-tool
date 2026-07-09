from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.middleware_trace import trace_id_var
from app.schemas.common import ErrorBody, ErrorEnvelope


def _sanitize_item(obj: object) -> object:
    """Recursively replace Exception instances with their string representation.

    Pydantic ``field_validator`` errors place the raw exception in ``ctx["error"]``,
    which is not JSON-serialisable.  This walk converts those to strings before
    the payload is handed to ``JSONResponse``.

    The ``isinstance(Exception)`` guard is checked first so it applies uniformly
    regardless of nesting depth — top-level, dict value, or list item.
    """
    if isinstance(obj, Exception):
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
        return _envelope("HTTP_ERROR", str(exc.detail), [], exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _envelope("VALIDATION_ERROR", "Invalid request", _sanitize_errors(list(exc.errors())), 422)
