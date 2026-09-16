"""Auth provider boundary.

Parity with ``app.storage.base.StorageBackend``: the structural contract every OIDC/OAuth
provider adapter must satisfy.
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
