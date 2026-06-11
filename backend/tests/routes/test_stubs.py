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
