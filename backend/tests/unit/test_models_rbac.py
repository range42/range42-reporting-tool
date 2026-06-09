from app.models.exercise_role import ExerciseRole
from app.models.role_definition import RoleDefinition


def test_role_definition_table_and_columns() -> None:
    assert RoleDefinition.__tablename__ == "role_definition"
    cols = RoleDefinition.__table__.columns
    assert {
        "id",
        "role_key",
        "display_label",
        "description",
        "permissions",
        "is_system",
        "created_at",
        "updated_at",
    } <= set(cols.keys())
    assert cols["role_key"].unique is True
    assert cols["is_system"].nullable is False


def test_exercise_role_table_and_unique() -> None:
    assert ExerciseRole.__tablename__ == "exercise_role"
    cols = ExerciseRole.__table__.columns
    assert {"id", "exercise_id", "user_id", "role_key", "created_at"} <= set(cols.keys())
    assert "updated_at" not in cols
    uniques = {
        tuple(sorted(c.name for c in con.columns))
        for con in ExerciseRole.__table__.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    }
    assert ("exercise_id", "role_key", "user_id") in uniques
