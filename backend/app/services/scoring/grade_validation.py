"""Grade-mode write validation.

THE SOLE INTERPRETER OF ``grade_mode`` ON WRITE. The rollup imports this module rather than
re-deriving the mode table.

Pure and DB-free: a function of ``(TemplateSectionDef, SectionGradeUpsert)`` only. Raises
:class:`GradeValidationError`; the route maps it to a 422 (repo convention — services raise
domain errors, routes map them).

The mode table:

===========  ============================  ===============================  ======================
grade_mode   required                      forbidden                        stored
===========  ============================  ===============================  ======================
numeric      grade in [min, max]           pass_fail_result, rubric_scores  grade
pass_fail    pass_fail_result              grade, rubric_scores             pass_fail_result + 1/0
rubric       rubric_scores within criteria grade, pass_fail_result          rubric_scores + pre-rolled grade
not_graded   --                            everything                       no row, ever
===========  ============================  ===============================  ======================
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.models.template_section_def import TemplateSectionDef
from app.schemas.evaluation import SectionGradeUpsert
from app.services.scoring import rollup

# Error codes; the route surfaces these verbatim as ``detail["error"]``.
INVALID_FOR_MODE = "invalid_grade_for_mode"
NOT_GRADED = "section_not_graded"
NO_RUBRIC_CRITERIA = "section_has_no_rubric_criteria"

# Pass/fail is stored as 0/1; the rollup applies the grade_max scaling.
_PASS = Decimal("1")
_FAIL = Decimal("0")

ValidatedGrade = tuple[Decimal | None, bool | None, list[dict[str, Any]] | None]


class GradeValidationError(Exception):
    """A payload that does not fit its section's ``grade_mode``. ``code`` is the wire error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _dec(v: object) -> Decimal | None:
    """DB scalar (the grade_* columns are Float) or JSONB number -> Decimal via str, so no
    binary-float error ever reaches the arithmetic. Never route a value through float() first."""
    return None if v is None else Decimal(str(v))


def _reject_other_channels(body: SectionGradeUpsert, allowed: str) -> None:
    """One grading channel per row — every channel but ``allowed`` must be unset."""
    for channel in ("grade", "pass_fail_result", "rubric_scores"):
        if channel != allowed and getattr(body, channel) is not None:
            raise GradeValidationError(INVALID_FOR_MODE)


def _validate_numeric(defn: TemplateSectionDef, body: SectionGradeUpsert) -> ValidatedGrade:
    _reject_other_channels(body, "grade")
    if body.grade is None:
        raise GradeValidationError(INVALID_FOR_MODE)
    low, high = _dec(defn.grade_min), _dec(defn.grade_max)
    # Bounds are inclusive: grade == grade_min and grade == grade_max are both valid.
    if (low is not None and body.grade < low) or (high is not None and body.grade > high):
        raise GradeValidationError(INVALID_FOR_MODE)
    return body.grade, None, None


def _validate_pass_fail(_defn: TemplateSectionDef, body: SectionGradeUpsert) -> ValidatedGrade:
    _reject_other_channels(body, "pass_fail_result")
    if body.pass_fail_result is None:
        raise GradeValidationError(INVALID_FOR_MODE)
    return (_PASS if body.pass_fail_result else _FAIL), body.pass_fail_result, None


def _validate_rubric(defn: TemplateSectionDef, body: SectionGradeUpsert) -> ValidatedGrade:
    _reject_other_channels(body, "rubric_scores")
    # A template misconfiguration the authoring layer does not forbid. 422, never a 500.
    if not defn.rubric_criteria:
        raise GradeValidationError(NO_RUBRIC_CRITERIA)
    if body.rubric_scores is None:
        raise GradeValidationError(INVALID_FOR_MODE)
    maxima = {str(c.get("name")): _dec(c.get("max_score", 0)) for c in defn.rubric_criteria}
    scored: list[dict[str, Any]] = []
    for entry in body.rubric_scores:
        ceiling = maxima.get(entry.criterion)
        if ceiling is None or entry.score < 0 or entry.score > ceiling:
            raise GradeValidationError(INVALID_FOR_MODE)
        # score as str, not float: JSONB has no Decimal, and a float would lose precision.
        scored.append({"criterion": entry.criterion, "score": str(entry.score), "note": entry.note})
    # Pre-roll the criteria into the section's own grade and persist it alongside the scores,
    # so the rollup reads one number per section. rollup.compute_rubric_rollup owns the formula.
    grade = rollup.compute_rubric_rollup(
        defn.rubric_criteria, scored, grade_min=_dec(defn.grade_min), grade_max=_dec(defn.grade_max)
    )
    return grade, None, scored


_VALIDATORS = {
    "numeric": _validate_numeric,
    "pass_fail": _validate_pass_fail,
    "rubric": _validate_rubric,
}


def validate_grade_payload(defn: TemplateSectionDef, body: SectionGradeUpsert) -> ValidatedGrade:
    """Return ``(grade, pass_fail_result, rubric_scores)`` to persist, or raise.

    ``not_graded`` never yields a row: both the finalize condition and the rollup rule read the
    *absence* of a ``section_grade``, so creating one would corrupt both.
    """
    if defn.grade_mode == "not_graded":
        raise GradeValidationError(NOT_GRADED)
    validator = _VALIDATORS.get(defn.grade_mode)
    if validator is None:
        raise GradeValidationError(INVALID_FOR_MODE)
    return validator(defn, body)
