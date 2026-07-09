"""Authlib Authorization-Code + PKCE adapter implementing ``AuthProvider``.

Login URL building and PKCE-challenge plumbing are synchronous string work; the
token exchange uses Authlib's ``AsyncOAuth2Client`` (httpx-backed, so a test
transport can target the in-process fake IdP); id_token validation delegates to
``core.security.verify_provider_id_token`` (JWKS, RS256).
"""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client

from app.auth.base import NormalizedClaims, RawToken
from app.core.security import SigningKeyResolver, verify_provider_id_token


@dataclass(frozen=True)
class OIDCMetadata:
    """The subset of OIDC discovery metadata the adapter needs."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str


class OIDCProvider:
    """Concrete ``AuthProvider`` for any OIDC-compliant IdP (Auth-Code + PKCE)."""

    def __init__(
        self,
        *,
        metadata: OIDCMetadata,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: str,
        jwks_resolver: SigningKeyResolver,
        transport: httpx.ASGITransport | None = None,
    ) -> None:
        self.metadata = metadata
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        self._jwks_resolver = jwks_resolver
        self._transport = transport

    def build_login_url(self, state: str, challenge: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{self.metadata.authorization_endpoint}?{urlencode(params)}"

    async def exchange(self, code: str, code_verifier: str) -> RawToken:
        async with AsyncOAuth2Client(
            self.client_id,
            self.client_secret,
            redirect_uri=self.redirect_uri,
            token_endpoint_auth_method="client_secret_post",
            transport=self._transport,
        ) as client:
            token = await client.fetch_token(
                self.metadata.token_endpoint,
                grant_type="authorization_code",
                code=code,
                code_verifier=code_verifier,
                redirect_uri=self.redirect_uri,
            )
        return str(token["id_token"])

    def claims(self, token: RawToken) -> NormalizedClaims:
        data = verify_provider_id_token(
            token,
            jwks_resolver=self._jwks_resolver,
            issuer=self.metadata.issuer,
            audience=self.client_id,
        )
        email = str(data.get("email") or "")
        display = str(data.get("name") or data.get("preferred_username") or email or data["sub"])
        picture = data.get("picture")
        return NormalizedClaims(
            subject=str(data["sub"]),
            email=email,
            display_name=display,
            provider="oidc",
            avatar_url=str(picture) if picture else None,
        )
