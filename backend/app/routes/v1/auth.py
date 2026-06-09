"""Authentication endpoints (design §4.5 / §6.1).

OIDC Auth-Code + PKCE: ``/auth/login`` stashes ``state`` + ``code_verifier`` in the
signed session cookie (SessionMiddleware) and redirects to the IdP; ``/auth/callback``
validates ``state``, exchanges the code, verifies the id_token, and issues an
app-JWT + ``user_session`` row. Refresh/logout/me and emergency-login land in
B14/B15.
"""

from authlib.common.security import generate_token
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from app.auth.emergency import emergency_claims, verify_emergency_password
from app.auth.oidc import OIDCProvider
from app.auth.session import RefreshDenied, refresh_session, revoke_session, start_session
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.rbac import AuthContext, get_auth_context, get_oidc_provider
from app.schemas.auth import TokenResponse, UserOut
from app.schemas.common import DataEnvelope

router = APIRouter(tags=["auth"])


@router.get("/auth/login")
async def login(request: Request, provider: OIDCProvider = Depends(get_oidc_provider)) -> RedirectResponse:
    verifier = generate_token(48)
    state = generate_token(24)
    challenge = create_s256_code_challenge(verifier)
    request.session["oidc_state"] = state
    request.session["oidc_verifier"] = verifier
    return RedirectResponse(provider.build_login_url(state, challenge), status_code=302)


@router.get("/auth/callback")
async def callback(
    request: Request,
    code: str,
    state: str,
    provider: OIDCProvider = Depends(get_oidc_provider),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DataEnvelope[TokenResponse]:
    expected_state = request.session.pop("oidc_state", None)
    verifier = request.session.pop("oidc_verifier", None)
    if not expected_state or expected_state != state or not verifier:
        raise HTTPException(status_code=400, detail="invalid oidc state")
    id_token = await provider.exchange(code, verifier)
    claims = provider.claims(id_token)
    issued = await start_session(db, claims, settings)
    return DataEnvelope(data=TokenResponse(access_token=issued.token, user=UserOut.from_model(issued.user)))


@router.get("/auth/me")
async def me(ctx: AuthContext = Depends(get_auth_context)) -> DataEnvelope[UserOut]:
    return DataEnvelope(data=UserOut.from_model(ctx.user))


@router.post("/auth/logout")
async def logout(
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[dict[str, bool]]:
    await revoke_session(db, ctx.session.jti)
    return DataEnvelope(data={"revoked": True})


@router.post("/auth/refresh")
async def refresh(
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DataEnvelope[TokenResponse]:
    try:
        token = await refresh_session(db, ctx.session, settings)
    except RefreshDenied as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return DataEnvelope(data=TokenResponse(access_token=token, user=UserOut.from_model(ctx.user)))


class EmergencyLoginIn(BaseModel):
    password: str


@router.post("/auth/emergency-login")
async def emergency_login(
    body: EmergencyLoginIn,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DataEnvelope[TokenResponse]:
    if not settings.emergency_admin_enabled:
        raise HTTPException(status_code=404, detail="not found")
    if not verify_emergency_password(body.password, settings.emergency_admin_password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    issued = await start_session(db, emergency_claims(), settings, force_global_admin=True)
    return DataEnvelope(data=TokenResponse(access_token=issued.token, user=UserOut.from_model(issued.user)))
