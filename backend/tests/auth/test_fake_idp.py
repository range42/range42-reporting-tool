from collections.abc import Callable
from typing import Any

import pytest

from app.core.security import InvalidProviderToken, verify_provider_id_token
from tests.auth.conftest import AUDIENCE, ISSUER


def test_minted_token_verifies(mint_id_token: Callable[..., str], idp_jwks_resolver: Any) -> None:
    token = mint_id_token()
    claims = verify_provider_id_token(token, jwks_resolver=idp_jwks_resolver, issuer=ISSUER, audience=AUDIENCE)
    assert claims["sub"] == "idp-subject-123"
    assert claims["email"] == "alice@idp.test"
    assert claims["picture"] == "https://idp.test/alice.png"


def test_wrong_audience_rejected(mint_id_token: Callable[..., str], idp_jwks_resolver: Any) -> None:
    token = mint_id_token(aud="someone-else")
    with pytest.raises(InvalidProviderToken):
        verify_provider_id_token(token, jwks_resolver=idp_jwks_resolver, issuer=ISSUER, audience=AUDIENCE)


def test_expired_token_rejected(mint_id_token: Callable[..., str], idp_jwks_resolver: Any) -> None:
    import time

    past = int(time.time()) - 600
    token = mint_id_token(iat=past, exp=past + 60)
    with pytest.raises(InvalidProviderToken):
        verify_provider_id_token(token, jwks_resolver=idp_jwks_resolver, issuer=ISSUER, audience=AUDIENCE)
