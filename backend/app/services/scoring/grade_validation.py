"""Grade-mode write validation (WP5 W5-1, L8).

THE SOLE INTERPRETER OF ``grade_mode`` ON WRITE. W5-2's rollup imports this module rather
than re-deriving the mode table; a second copy of these rules is how the two slices drift.

Pure and DB-free: a function of ``(TemplateSectionDef, SectionGradeUpsert)`` only, so the
whole table is unit-testable without a database. Raises :class:`GradeValidationError`; the
route maps it to a 422 (repo convention — services raise domain errors, routes map them,
matching ``state_machine.InvalidTransition``).

The mode table:

===========  ============================  ===============================  ======================
grade_mode   required                      forbidden                        stored
===========  ============================  ===============================  ======================
numeric      grade in [min, max]           pass_fail_result, rubric_scores  grade
pass_fail    pass_fail_result              grade, rubric_scores             pass_fail_result + 1/0
rubric       rubric_scores within criteria grade, pass_fail_result          rubric_scores
not_graded   --                            everything                       no row, ever
===========  ============================  ===============================  ======================
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.models.template_section_def import TemplateSectionDef
from app.schemas.evaluation import SectionGradeUpsert

# Error codes; the route surfaces these verbatim as ``detail["error"]``.
INVALID_FOR_MODE = "invalid_grade_for_mode"
NOT_GRADED = "section_not_graded"
NO_RUBRIC_CRITERIA = "section_has_no_rubric_criteria"

# A4 — pass/fail is stored as 0/1; W5-2's rollup applies the grade_max scaling.
_PASS = Decimal("1")
_FAIL = Decimal("0")

ValidatedGrade = tuple[Decimal | None, bool | None, list[dict[str, Any]] | None]


class GradeValidationError(Exception):
    """A payload that does not fit its section's ``grade_mode``. ``code`` is the wire error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _dec(v: float | None) -> Decimal | None:
    """Float column -> Decimal without binary-float artefacts (grade_* are Float in the DB)."""
    return None if v is None else Decimal(str(v))


def _reject_other_channels(body: SectionGradeUpsert, allowed: str) -> None:
    """One grading channel per row (§4.2) — every channel but ``allowed`` must be unset."""
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
    # Edge case 15 — a template misconfiguration WP3 does not forbid. 422, never a 500.
    if not defn.rubric_criteria:
        raise GradeValidationError(NO_RUBRIC_CRITERIA)
    if body.rubric_scores is None:
        raise GradeValidationError(INVALID_FOR_MODE)
    maxima = {str(c.get("name")): _dec(float(c.get("max_score", 0))) for c in defn.rubric_criteria}
    scored: list[dict[str, Any]] = []
    for entry in body.rubric_scores:
        ceiling = maxima.get(entry.criterion)
        if ceiling is None or entry.score < 0 or entry.score > ceiling:
            raise GradeValidationError(INVALID_FOR_MODE)
        # score as str, not float: JSONB has no Decimal and a float here would bite W5-2.
        scored.append({"criterion": entry.criterion, "score": str(entry.score), "note": entry.note})
    # grade stays NULL — W5-2's pre-rollup derives the number from these scores.
    return None, None, scored


_VALIDATORS = {
    "numeric": _validate_numeric,
    "pass_fail": _validate_pass_fail,
    "rubric": _validate_rubric,
}


def validate_grade_payload(defn: TemplateSectionDef, body: SectionGradeUpsert) -> ValidatedGrade:
    """Return ``(grade, pass_fail_result, rubric_scores)`` to persist, or raise.

    ``not_graded`` never yields a row: §7.2's finalize condition and §4.2's rollup rule both
    read the *absence* of a ``section_grade``, so creating one would corrupt both.
    """
    if defn.grade_mode == "not_graded":
        raise GradeValidationError(NOT_GRADED)
    validator = _VALIDATORS.get(defn.grade_mode)
    if validator is None:
        raise GradeValidationError(INVALID_FOR_MODE)
    return validator(defn, body)
