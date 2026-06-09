from app.auth.base import AuthProvider, NormalizedClaims, RawToken


class _FakeProvider:
    """A structurally-typed fake; must satisfy the AuthProvider Protocol."""

    def build_login_url(self, state: str, challenge: str) -> str:
        return f"https://idp.example/auth?state={state}&challenge={challenge}"

    async def exchange(self, code: str, code_verifier: str) -> RawToken:
        return f"token-for-{code}-{code_verifier}"

    def claims(self, token: RawToken) -> NormalizedClaims:
        return NormalizedClaims(
            subject="sub-1",
            email="user@example.com",
            display_name="User One",
            provider="fake",
        )


def test_fake_provider_satisfies_protocol() -> None:
    provider: AuthProvider = _FakeProvider()
    assert provider.build_login_url("s", "c").startswith("https://")


def test_normalized_claims_fields() -> None:
    claims = NormalizedClaims(
        subject="sub-1",
        email="user@example.com",
        display_name="User One",
        provider="fake",
    )
    assert claims.subject == "sub-1"
    assert claims.email == "user@example.com"
    assert claims.display_name == "User One"
    assert claims.provider == "fake"


def test_normalized_claims_avatar_defaults_none() -> None:
    claims = NormalizedClaims(subject="s", email="e@x", display_name="D", provider="oidc")
    assert claims.avatar_url is None


def test_normalized_claims_avatar_set() -> None:
    claims = NormalizedClaims(
        subject="s", email="e@x", display_name="D", provider="oidc", avatar_url="https://img/a.png"
    )
    assert claims.avatar_url == "https://img/a.png"
