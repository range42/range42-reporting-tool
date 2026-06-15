import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import jwt
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.auth.oidc import OIDCMetadata, OIDCProvider
from app.core.config import Settings, get_settings
from app.core.db import build_engine, get_sessionmaker
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware_trace import TraceIdMiddleware
from app.routes.v1 import _schema_probe as schema_probe_route  # SCAFFOLDING (F4)
from app.routes.v1 import auth as auth_route
from app.routes.v1 import config as config_route
from app.routes.v1 import exercises as exercises_route
from app.routes.v1 import health as health_route
from app.routes.v1 import permissions as permissions_route
from app.routes.v1 import ping as ping_route
from app.routes.v1 import roles as roles_route
from app.routes.v1 import teams as teams_route
from app.routes.v1 import templates as templates_route
from app.routes.v1._stubs import routers as stub_routers

logger = structlog.get_logger(__name__)


async def _build_oidc_provider(settings: Settings) -> OIDCProvider | None:
    """Discover OIDC metadata at boot. Returns None if unconfigured/unreachable
    (the app still boots; ``get_oidc_provider`` then answers 503)."""
    if not settings.oidc_issuer_url or not settings.oidc_client_id:
        return None
    discovery_url = settings.oidc_issuer_url.rstrip("/") + "/.well-known/openid-configuration"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            doc = (await client.get(discovery_url)).raise_for_status().json()
        jwks_resolver = jwt.PyJWKClient(doc["jwks_uri"])
        return OIDCProvider(
            metadata=OIDCMetadata(
                issuer=doc["issuer"],
                authorization_endpoint=doc["authorization_endpoint"],
                token_endpoint=doc["token_endpoint"],
                jwks_uri=doc["jwks_uri"],
            ),
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret,
            redirect_uri=settings.oidc_redirect_uri,
            scopes=settings.oidc_scopes,
            jwks_resolver=jwks_resolver,
        )
    except Exception as exc:  # noqa: BLE001 — boot must survive a down/misconfigured IdP
        logger.warning("oidc_discovery_failed", issuer=settings.oidc_issuer_url, error=str(exc))
        return None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Build the async DB engine + sessionmaker once per process and expose them
    # on app.state for request handlers (e.g. the /health DB ping).
    settings = get_settings()
    app.state.db_engine = build_engine(settings.database_url)
    app.state.db_sessionmaker = get_sessionmaker(app.state.db_engine)
    app.state.oidc_provider = await _build_oidc_provider(settings)
    try:
        yield
    finally:
        await app.state.db_engine.dispose()


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(
        title="range42-reporting-tool",
        version=settings.app_version,
        lifespan=lifespan,
    )
    app.state.oidc_provider = None
    app.add_middleware(TraceIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list or ["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    session_secret = hashlib.sha256(b"session:" + settings.jwt_secret.encode()).hexdigest()
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret,
        session_cookie="rt_oidc_txn",
        https_only=settings.session_https_only,
        same_site="lax",
        max_age=300,
    )
    register_error_handlers(app)
    for r in (
        ping_route.router,
        health_route.router,
        config_route.router,
        auth_route.router,
        exercises_route.router,
        teams_route.router,
        roles_route.router,
        permissions_route.router,
        templates_route.router,
    ):
        app.include_router(r, prefix="/api/v1")
    # SCAFFOLDING (F4): probe route exists only to emit the SectionBody
    # discriminator into OpenAPI / generated frontend types. Removable in WP3.
    app.include_router(schema_probe_route.router, prefix="/api/v1")
    for r in stub_routers.values():
        app.include_router(r, prefix="/api/v1")
    return app


app = create_app()
