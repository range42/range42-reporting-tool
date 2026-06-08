import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Receive, Scope, Send

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


class TraceIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        trace_id_var.set(uuid.uuid4().hex)
        await self.app(scope, receive, send)
