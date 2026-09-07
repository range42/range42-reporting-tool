"""A7/M2 as an executable contract: only ``rollup.py`` writes the grade columns.

The sole-writer rule is what makes the grade auditable — one module to read, one place a
number can come from. It is easy to state in a docstring and easy to break with one
well-meaning assignment in a route, so it is checked here by reading the source tree.

Cheap and blunt on purpose: a static scan cannot be defeated by a test that forgets to
exercise the new write path.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
SOLE_WRITER = "services/scoring/rollup.py"

# Attribute assignment, not a keyword argument or a comparison: `x.overall_grade = ...`.
_ASSIGNMENT = re.compile(r"\.(overall_grade|grade_version)\s*=(?!=)")


def _offending_files(column_pattern: re.Pattern[str]) -> set[str]:
    return {path.relative_to(APP).as_posix() for path in APP.rglob("*.py") if column_pattern.search(path.read_text())}


def test_report_overall_grade_is_only_ever_written_by_rollup() -> None:
    # Arrange / Act
    writers = _offending_files(re.compile(r"\.overall_grade\s*=(?!=)"))

    # Assert
    assert writers == {SOLE_WRITER}, f"overall_grade written outside the sole writer: {writers - {SOLE_WRITER}}"


def test_grade_version_is_only_ever_written_by_rollup() -> None:
    """D3: the counter is incremented in exactly one function, so it cannot go backwards."""
    # Arrange / Act
    writers = _offending_files(re.compile(r"\.grade_version\s*=(?!=)"))

    # Assert
    assert writers == {SOLE_WRITER}, f"grade_version written outside the sole writer: {writers - {SOLE_WRITER}}"


def test_the_guard_would_notice_a_new_writer() -> None:
    """The regex has to match a real assignment and ignore a keyword argument.

    Without this, a typo in the pattern would make both tests above pass vacuously forever.
    """
    # Arrange / Act / Assert
    assert _ASSIGNMENT.search("report.overall_grade = new_grade")
    assert _ASSIGNMENT.search("report.grade_version = report.grade_version + 1")
    assert not _ASSIGNMENT.search("ReportOut(overall_grade=report.overall_grade)")
    assert not _ASSIGNMENT.search("if report.overall_grade == other:")
