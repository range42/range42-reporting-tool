from typing import Any

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[Any] = []


class ErrorEnvelope(BaseModel):
    error: ErrorBody
    trace_id: str | None = None


class ConflictDetail(BaseModel):
    """Payload carried in ``ErrorBody.details[]`` for 409 (optimistic-lock) responses.

    When a write loses an optimistic-concurrency race, the 409 error envelope's
    ``details`` array carries one of these so the client can reconcile against the
    current server state. Shape reservation — emitted by WP4+ write paths.
    """

    current_version: int
    current_content: str | None = None
    current_choice_values: list[str] | None = None


class Page(BaseModel):
    page: int = 1
    per_page: int = 25
    total: int = 0


class DataEnvelope[T](BaseModel):
    data: T
    meta: Page | None = None
