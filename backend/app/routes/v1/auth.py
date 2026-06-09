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
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from app.auth.oidc import OIDCProvider
from app.auth.session import start_session
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.rbac import get_oidc_provider
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
