from app.models import Exercise, ScoringConfig, Team, TeamMember, TeamTypeConfig
from app.models.base import Base


def test_domain_tables_registered() -> None:
    tables = set(Base.metadata.tables)
    assert {"exercise", "team", "team_type_config", "team_member", "scoring_config"} <= tables


def test_exercise_defaults_and_columns() -> None:
    cols = Exercise.__table__.c
    assert cols["status"].server_default is not None
    assert str(cols["status"].server_default.arg) == "'draft'"
    assert cols["name"].nullable is False
    assert "classification_caveats" in cols
    assert cols["created_by"].foreign_keys


def test_team_unique_name_per_exercise() -> None:
    uniques = {
        tuple(sorted(c.name for c in con.columns))
        for con in Team.__table__.constraints
        if hasattr(con, "columns") and con.name == "uq_team_name_per_exercise"
    }
    assert ("exercise_id", "name") in uniques


def test_scoring_config_one_per_exercise() -> None:
    assert ScoringConfig.__table__.c["exercise_id"].unique is True


def test_team_member_fks() -> None:
    assert TeamMember.__table__.c["team_id"].foreign_keys
    assert TeamMember.__table__.c["user_id"].foreign_keys


def test_team_type_config_type_key_not_null() -> None:
    assert TeamTypeConfig.__table__.c["type_key"].nullable is False
