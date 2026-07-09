import pytest
from pydantic import ValidationError

from app.schemas.domain import ExerciseCreate, ExerciseUpdate, TeamCreate, TeamTypeConfigUpdate, TeamUpdate
from app.schemas.role import RoleCreate, RoleUpdate


def test_exercise_update_rejects_bad_status() -> None:
    with pytest.raises(ValidationError):
        ExerciseUpdate(status="bogus")


def test_exercise_create_minimal() -> None:
    e = ExerciseCreate(name="Ex")
    assert e.name == "Ex"
    assert e.description is None


def test_role_create_validates_permissions() -> None:
    with pytest.raises(ValidationError):
        RoleCreate(role_key="x", display_label="X", permissions=["not:a:real:perm"])
    ok = RoleCreate(role_key="x", display_label="X", permissions=["exercises:read"])
    assert ok.permissions == ["exercises:read"]


def test_team_member_out_from_row() -> None:
    import uuid
    from datetime import UTC, datetime

    from app.models import TeamMember, User
    from app.schemas.domain import TeamMemberOut

    u = User(external_id="oidc:x", email="e@x.test", display_name="Me")
    u.id = uuid.uuid4()
    m = TeamMember(team_id=uuid.uuid4(), user_id=u.id)
    m.id = uuid.uuid4()
    m.created_at = datetime.now(UTC)

    out = TeamMemberOut.from_row(m, u)
    assert out.email == "e@x.test"
    assert out.display_name == "Me"
    assert out.user_id == str(u.id)
    assert out.id == str(m.id)


# ── NEW TESTS (RED phase — all must fail before production changes) ───────────


# ExerciseUpdate: explicit-null on required fields must be rejected (422)
def test_exercise_update_rejects_explicit_null_name() -> None:
    with pytest.raises(ValidationError):
        ExerciseUpdate(name=None)


def test_exercise_update_rejects_explicit_null_status() -> None:
    with pytest.raises(ValidationError):
        ExerciseUpdate(status=None)


# ExerciseUpdate: empty name rejected
def test_exercise_update_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        ExerciseUpdate(name="")


# ExerciseUpdate: description=None is allowed (nullable column)
def test_exercise_update_allows_null_description() -> None:
    u = ExerciseUpdate(description=None)
    assert u.description is None


# ExerciseUpdate: empty partial update is valid (no fields set)
def test_exercise_update_empty_is_valid() -> None:
    u = ExerciseUpdate()
    assert u.name is None
    assert u.status is None


# TeamUpdate: explicit-null on NOT NULL fields rejected
def test_team_update_rejects_explicit_null_team_type() -> None:
    with pytest.raises(ValidationError):
        TeamUpdate(team_type=None)


def test_team_update_rejects_explicit_null_name() -> None:
    with pytest.raises(ValidationError):
        TeamUpdate(name=None)


# TeamUpdate: invalid color rejected
def test_team_update_rejects_invalid_color() -> None:
    with pytest.raises(ValidationError):
        TeamUpdate(color="red")


# TeamUpdate: valid update works
def test_team_update_valid_name() -> None:
    u = TeamUpdate(name="A2")
    assert u.name == "A2"


# TeamCreate: empty name rejected
def test_team_create_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        TeamCreate(name="", team_type="blue")


# TeamCreate: invalid color rejected
def test_team_create_rejects_invalid_color() -> None:
    with pytest.raises(ValidationError):
        TeamCreate(name="A", team_type="blue", color="not-a-hex")


# TeamCreate: valid hex color accepted
def test_team_create_accepts_valid_color() -> None:
    t = TeamCreate(name="A", team_type="blue", color="#3B82F6")
    assert t.color == "#3B82F6"


# RoleUpdate: explicit-null on permissions rejected
def test_role_update_rejects_explicit_null_permissions() -> None:
    with pytest.raises(ValidationError):
        RoleUpdate(permissions=None)


# RoleUpdate: omitting permissions is fine (partial update)
def test_role_update_omitting_permissions_is_valid() -> None:
    u = RoleUpdate(display_label="New Label")
    assert u.permissions is None


# TeamTypeConfigUpdate: explicit-null on display_label rejected
def test_team_type_config_update_rejects_null_display_label() -> None:
    with pytest.raises(ValidationError):
        TeamTypeConfigUpdate(display_label=None)
