"""Task 6 — the §6.10 timeline shape (M15, M16)."""

from datetime import UTC, datetime
from decimal import Decimal

from app.services.scoring.rollup import EvaluationInput, GradeTimeline, SectionGradeInput
from app.services.scoring.timeline import ReportMeta, build_timeline_entry

EARLIER = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)
LATER = datetime(2026, 8, 31, 17, 30, tzinfo=UTC)

REPORT = ReportMeta(
    report_id="r1",
    report_name="SITREP #5",
    report_type="sitrep",
    template_id="t1",
    due_at=EARLIER,
    submitted_at=EARLIER,
)


def _s(grade: str | None, **kw) -> SectionGradeInput:
    base = dict(
        section_def_id="s1",
        name="Executive Summary",
        grade_mode="numeric",
        grade=None if grade is None else Decimal(grade),
        grade_min=Decimal("0"),
        grade_max=Decimal("10"),
        grade_weight=Decimal("1"),
        position=0,
    )
    return SectionGradeInput(**{**base, **kw})


def _ev(*sections: SectionGradeInput, weight: str = "1", eid: str = "e", completed=LATER) -> EvaluationInput:
    return EvaluationInput(
        evaluation_id=eid,
        evaluator_id=f"u-{eid}",
        aggregated_weight=Decimal(weight),
        sections=sections,
        completed_at=completed,
    )


def _entry(*evaluations: EvaluationInput, grade="8.00", version=3, manual=False):
    return build_timeline_entry(
        REPORT,
        evaluations,
        overall_grade=None if grade is None else Decimal(grade),
        grade_version=version,
        is_manual=manual,
    )


def test_timeline_entry_matches_the_architecture_6_10_field_set() -> None:
    entry = _entry(_ev(_s("8")))
    for field in (
        "report_id",
        "report_name",
        "report_type",
        "template_id",
        "due_at",
        "submitted_at",
        "evaluated_at",
        "overall_grade",
        "section_grades",
    ):
        assert hasattr(entry, field), field
    assert entry.report_name == "SITREP #5"
    assert entry.overall_grade == Decimal("8.00")


def test_timeline_section_grades_carry_scaled_values_not_raw_pass_fail() -> None:
    # Stored 1 must surface as 10 on a 0-10 section, never as the raw 1.
    entry = _entry(_ev(_s("1", grade_mode="pass_fail")))
    assert entry.section_grades[0].grade == Decimal("10.00")


def test_timeline_section_grades_omit_not_graded_sections() -> None:
    sections = (_s("8"), _s(None, section_def_id="s2", name="Service status", grade_mode="not_graded"))
    entry = _entry(_ev(*sections))
    assert [g.section_def_id for g in entry.section_grades] == ["s1"]


def test_timeline_lists_a_gradable_section_nobody_has_marked_yet() -> None:
    # Listed with a null grade rather than dropped, so a client can show it as outstanding.
    entry = _entry(_ev(_s("8"), _s(None, section_def_id="s2", name="Lessons learned")))
    assert [(g.section_def_id, g.grade) for g in entry.section_grades] == [
        ("s1", Decimal("8.00")),
        ("s2", None),
    ]


def test_timeline_section_grades_are_ordered_by_position() -> None:
    sections = (
        _s("7", section_def_id="third", name="Third", position=2),
        _s("8", section_def_id="first", name="First", position=0),
        _s("9", section_def_id="second", name="Second", position=1),
    )
    entry = _entry(_ev(*sections))
    assert [g.name for g in entry.section_grades] == ["First", "Second", "Third"]


def test_timeline_section_grades_carry_the_template_grade_weight() -> None:
    entry = _entry(_ev(_s("8", grade_weight=Decimal("2.5"))))
    assert entry.section_grades[0].weight == Decimal("2.5")


def test_timeline_evaluated_at_is_max_completed_at_across_evaluations() -> None:
    entry = _entry(
        _ev(_s("8"), eid="a", completed=EARLIER),
        _ev(_s("6"), eid="b", completed=LATER),
    )
    assert entry.evaluated_at == LATER


def test_timeline_evaluated_at_is_none_while_any_evaluation_is_outstanding() -> None:
    # M16 — "evaluated" means every assigned evaluator has finished.
    entry = _entry(
        _ev(_s("8"), eid="done", completed=LATER),
        _ev(_s("6"), eid="still-going", completed=None),
    )
    assert entry.evaluated_at is None


def test_timeline_evaluated_at_is_none_without_evaluations() -> None:
    assert _entry().evaluated_at is None


def test_timeline_carries_grade_version() -> None:
    # D3 — lets a consumer detect that a reopen superseded published numbers.
    assert _entry(_ev(_s("8")), version=7).grade_version == 7


def test_timeline_carries_is_manual_flag() -> None:
    assert _entry(_ev(_s("8")), manual=True).is_manual is True
    assert _entry(_ev(_s("8"))).is_manual is False


def test_timeline_carries_mixed_scale_flag() -> None:
    mixed = _ev(_s("8"), _s("80", section_def_id="s2", name="Percent", grade_max=Decimal("100")))
    assert _entry(mixed).mixed_scale is True
    assert _entry(_ev(_s("8"))).mixed_scale is False


def test_timeline_carries_evaluator_count() -> None:
    assert _entry(_ev(_s("8"), eid="a"), _ev(_s("6"), eid="b")).evaluator_count == 2


def test_timeline_multi_evaluator_section_grade_is_the_aggregated_value() -> None:
    # Same section graded 9 and 5 at weights 3 and 1 -> (27+5)/4 = 8.
    entry = _entry(
        _ev(_s("9"), weight="3", eid="lead"),
        _ev(_s("5"), weight="1", eid="shadow"),
    )
    assert entry.section_grades[0].grade == Decimal("8.00")


def test_grade_timeline_name_is_still_importable_from_rollup() -> None:
    # Keeps tests/unit/test_services_stubs.py::test_scoring_rollup_is_implemented honest.
    timeline = GradeTimeline(report_id="r1", overall_grade=Decimal("8.00"), grade_version=2)
    assert timeline.report_id == "r1"
    assert timeline.entry is None
