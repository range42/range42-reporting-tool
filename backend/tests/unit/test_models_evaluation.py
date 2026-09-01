from app.models import Evaluation, Report, ScoringConfig, SectionGrade
from app.models.base import Base


def test_evaluation_table_name_and_unique_constraint() -> None:
    assert Evaluation.__tablename__ == "evaluation"
    assert "evaluation" in set(Base.metadata.tables)
    cols = Evaluation.__table__.columns
    assert {
        "id",
        "report_id",
        "evaluator_id",
        "status",
        "overall_feedback",
        "overall_grade",
        "aggregated_weight",
        "completed_at",
        "reopen_count",
        "reopened_at",
        "reopened_by",
        "assigned_by",
        "created_at",
        "updated_at",
    } <= set(cols.keys())
    uniques = {
        tuple(sorted(c.name for c in con.columns))
        for con in Evaluation.__table__.constraints
        if con.name == "uq_evaluation_report_evaluator"
    }
    assert ("evaluator_id", "report_id") in uniques


def test_evaluation_status_defaults_to_assigned() -> None:
    col = Evaluation.__table__.c["status"]
    assert col.nullable is False
    assert col.server_default is not None
    assert str(col.server_default.arg) == "'assigned'"


def test_evaluation_aggregated_weight_defaults_to_one() -> None:
    col = Evaluation.__table__.c["aggregated_weight"]
    assert col.nullable is False
    assert col.server_default is not None
    assert str(col.server_default.arg) == "1.0"


def test_evaluation_evaluator_id_is_not_nullable() -> None:
    cols = Evaluation.__table__.c
    assert cols["evaluator_id"].nullable is False
    assert cols["evaluator_id"].foreign_keys
    assert cols["report_id"].nullable is False
    assert cols["assigned_by"].nullable is False
    assert cols["reopened_by"].nullable is True


def test_section_grade_table_name_and_unique_constraint() -> None:
    assert SectionGrade.__tablename__ == "section_grade"
    assert "section_grade" in set(Base.metadata.tables)
    cols = SectionGrade.__table__.columns
    assert {
        "id",
        "evaluation_id",
        "report_section_id",
        "grade",
        "pass_fail_result",
        "rubric_scores",
        "feedback",
        "graded_by",
        "created_at",
        "updated_at",
    } <= set(cols.keys())
    uniques = {
        tuple(sorted(c.name for c in con.columns))
        for con in SectionGrade.__table__.constraints
        if con.name == "uq_section_grade_eval_section"
    }
    assert ("evaluation_id", "report_section_id") in uniques


def test_section_grade_grade_is_nullable_for_not_graded_and_rubric() -> None:
    cols = SectionGrade.__table__.c
    assert cols["grade"].nullable is True
    assert cols["pass_fail_result"].nullable is True
    assert cols["rubric_scores"].nullable is True
    assert cols["evaluation_id"].nullable is False
    assert cols["graded_by"].nullable is False


def test_report_grade_version_column_defaults_to_zero() -> None:
    col = Report.__table__.c["grade_version"]
    assert col.nullable is False
    assert col.server_default is not None
    assert str(col.server_default.arg) == "0"


def test_report_overall_grade_is_manual_defaults_to_false() -> None:
    cols = Report.__table__.c
    assert cols["overall_grade"].nullable is True
    assert cols["overall_feedback"].nullable is True
    col = cols["overall_grade_is_manual"]
    assert col.nullable is False
    assert str(col.server_default.arg) == "false"


def test_scoring_config_finalize_policy_defaults_to_all_must_finalize() -> None:
    col = ScoringConfig.__table__.c["finalize_policy"]
    assert col.nullable is False
    assert col.server_default is not None
    assert str(col.server_default.arg) == "'all_must_finalize'"
