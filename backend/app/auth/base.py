"""Auth provider boundary (shape reservation — no implementation yet).

Parity with ``app.storage.base.StorageBackend``: defines the structural contract
every OIDC/OAuth provider adapter must satisfy. Concrete providers and the token
exchange / JWKS validation land in WP2; this module only locks the interface so
later work does not retrofit it.
"""

from dataclasses import dataclass
from typing import Protocol

# A raw provider token (e.g. the encoded id_token / access_token string) as
# returned by the provider's token endpoint. Kept as an alias so the Protocol
# signature reads as intent; the concrete shape is provider-specific.
type RawToken = str


@dataclass(frozen=True)
class NormalizedClaims:
    """Provider-agnostic identity claims, normalized across every adapter."""

    subject: str
    email: str
    display_name: str
    provider: str
    avatar_url: str | None = None


class AuthProvider(Protocol):
    """Structural contract for an OIDC/OAuth identity provider adapter."""

    def build_login_url(self, state: str, challenge: str) -> str: ...

    async def exchange(self, code: str, code_verifier: str) -> RawToken: ...

    def claims(self, token: RawToken) -> NormalizedClaims: ...
