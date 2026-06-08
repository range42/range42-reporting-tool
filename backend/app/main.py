from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware_trace import TraceIdMiddleware
from app.routes.v1 import config as config_route
from app.routes.v1 import health as health_route
from app.routes.v1 import ping as ping_route


def create_app() -> FastAPI:
    configure_logging()
    settings = Settings()
    app = FastAPI(title="range42-reporting-tool", version=settings.app_version)
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
    return app


app = create_app()
