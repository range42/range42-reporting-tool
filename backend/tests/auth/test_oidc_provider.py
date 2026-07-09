from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.auth.oidc import OIDCMetadata, OIDCProvider
from tests.auth.conftest import (
    AUDIENCE,
    AUTHORIZATION_ENDPOINT,
    ISSUER,
    JWKS_URI,
    TOKEN_ENDPOINT,
)


def _provider(transport: httpx.ASGITransport | None, resolver: Any) -> OIDCProvider:
    return OIDCProvider(
        metadata=OIDCMetadata(
            issuer=ISSUER,
            authorization_endpoint=AUTHORIZATION_ENDPOINT,
            token_endpoint=TOKEN_ENDPOINT,
            jwks_uri=JWKS_URI,
        ),
        client_id=AUDIENCE,
        client_secret="shh",
        redirect_uri="https://app.test/api/v1/auth/callback",
        scopes="openid profile email",
        jwks_resolver=resolver,
        transport=transport,
    )


def test_build_login_url_has_pkce_params(idp_jwks_resolver: Any) -> None:
    url = _provider(None, idp_jwks_resolver).build_login_url(state="st-1", challenge="ch-1")
    q = parse_qs(urlparse(url).query)
    assert url.startswith(AUTHORIZATION_ENDPOINT)
    assert q["response_type"] == ["code"]
    assert q["client_id"] == [AUDIENCE]
    assert q["state"] == ["st-1"]
    assert q["code_challenge"] == ["ch-1"]
    assert q["code_challenge_method"] == ["S256"]
    assert q["scope"] == ["openid profile email"]


@pytest.mark.asyncio
async def test_exchange_then_claims(fake_idp_transport: httpx.ASGITransport, idp_jwks_resolver: Any) -> None:
    provider = _provider(fake_idp_transport, idp_jwks_resolver)
    id_token = await provider.exchange("auth-code", "verifier-xyz")
    claims = provider.claims(id_token)
    assert claims.provider == "oidc"
    assert claims.subject == "idp-subject-123"
    assert claims.email == "alice@idp.test"
    assert claims.display_name == "Alice Example"
    assert claims.avatar_url == "https://idp.test/alice.png"
