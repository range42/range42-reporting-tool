from app.routes.v1._stubs import GROUPS


def test_auth_is_no_longer_a_stub() -> None:
    # The real auth router (routes/v1/auth.py) replaces the reserved empty stub.
    assert "auth" not in GROUPS


def test_exercises_is_no_longer_a_stub() -> None:
    # The real exercises router (routes/v1/exercises.py) replaces the reserved empty stub.
    assert "exercises" not in GROUPS


def test_teams_is_no_longer_a_stub() -> None:
    # The real teams router (routes/v1/teams.py) replaces the reserved empty stub.
    assert "teams" not in GROUPS


def test_roles_is_no_longer_a_stub() -> None:
    # The real roles router (routes/v1/roles.py) replaces the reserved empty stub.
    assert "roles" not in GROUPS


def test_campaigns_is_no_longer_a_stub() -> None:
    # The real campaigns router (routes/v1/campaigns.py) replaces the reserved empty stub.
    assert "campaigns" not in GROUPS
