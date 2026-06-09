from app.routes.v1._stubs import GROUPS


def test_auth_is_no_longer_a_stub() -> None:
    # The real auth router (routes/v1/auth.py) replaces the reserved empty stub.
    assert "auth" not in GROUPS
