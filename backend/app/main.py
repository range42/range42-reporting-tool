from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings
from app.core.db import build_engine, get_sessionmaker
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware_trace import TraceIdMiddleware
from app.routes.v1 import _schema_probe as schema_probe_route  # SCAFFOLDING (F4)
from app.routes.v1 import config as config_route
from app.routes.v1 import health as health_route
from app.routes.v1 import ping as ping_route
from app.routes.v1._stubs import routers as stub_routers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Build the async DB engine + sessionmaker once per process and expose them
    # on app.state for request handlers (e.g. the /health DB ping).
    settings = Settings()
    app.state.db_engine = build_engine(settings.database_url)
    app.state.db_sessionmaker = get_sessionmaker(app.state.db_engine)
    try:
        yield
    finally:
        await app.state.db_engine.dispose()


def create_app() -> FastAPI:
    configure_logging()
    settings = Settings()
    app = FastAPI(
        title="range42-reporting-tool",
        version=settings.app_version,
        lifespan=lifespan,
    )
    app.add_middleware(TraceIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list or ["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    for r in (ping_route.router, health_route.router, config_route.router):
        app.include_router(r, prefix="/api/v1")
    # SCAFFOLDING (F4): probe route exists only to emit the SectionBody
    # discriminator into OpenAPI / generated frontend types. Removable in WP3.
    app.include_router(schema_probe_route.router, prefix="/api/v1")
    for r in stub_routers.values():
        app.include_router(r, prefix="/api/v1")
    return app


app = create_app()
