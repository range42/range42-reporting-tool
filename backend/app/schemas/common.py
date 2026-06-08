from typing import Any

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[Any] = []


class ErrorEnvelope(BaseModel):
    error: ErrorBody
    trace_id: str | None = None


class Page(BaseModel):
    page: int = 1
    per_page: int = 25
    total: int = 0


class DataEnvelope[T](BaseModel):
    data: T
    meta: Page | None = None
