from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.middleware_trace import trace_id_var
from app.schemas.common import ErrorBody, ErrorEnvelope


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
        return _envelope("VALIDATION_ERROR", "Invalid request", list(exc.errors()), 422)
