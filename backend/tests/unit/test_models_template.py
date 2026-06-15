from app.models.report_template import ReportTemplate
from app.models.template_section_def import TemplateSectionDef


def test_report_template_table_and_columns() -> None:
    assert ReportTemplate.__tablename__ == "report_template"
    cols = ReportTemplate.__table__.columns
    assert {
        "id",
        "lineage_id",
        "version",
        "name",
        "report_type",
        "description",
        "status",
        "metadata_",
        "created_by",
        "created_at",
        "updated_at",
    } <= set(cols.keys())
    uniques = {
        tuple(sorted(c.name for c in con.columns))
        for con in ReportTemplate.__table__.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    }
    assert ("lineage_id", "version") in uniques


def test_template_section_def_table_and_columns() -> None:
    assert TemplateSectionDef.__tablename__ == "template_section_def"
    cols = TemplateSectionDef.__table__.columns
    assert {
        "id",
        "template_id",
        "position",
        "name",
        "description",
        "field_type",
        "char_limit",
        "is_required",
        "grade_mode",
        "grade_min",
        "grade_max",
        "grade_weight",
        "rubric_criteria",
        "evaluation_criteria",
        "choice_config",
        "mitre_attack_tags",
        "capec_tags",
        "cwe_tags",
        "created_at",
        "updated_at",
    } <= set(cols.keys())
    assert cols["template_id"].nullable is False
