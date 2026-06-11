import pytest
from pydantic import ValidationError

from app.schemas.domain import ExerciseCreate, ExerciseUpdate
from app.schemas.role import RoleCreate


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
