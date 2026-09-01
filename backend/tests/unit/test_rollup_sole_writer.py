"""Task 10 — the A7/M2 sole-writer contract, enforced against the source itself.

Docstrings claiming "only rollup.py writes this" are not enforcement; the next person adding a
route will not read them. These walk every module under ``app/`` with ``ast`` and fail if any
file other than ``rollup.py`` assigns the grade fields.

``ast`` rather than a regex on purpose: a docstring or comment mentioning ``overall_grade``
must not trip the guard, and only real assignment targets should.
"""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
ROLLUP = "app/services/scoring/rollup.py"


def _python_files() -> list[Path]:
    return sorted(p for p in APP.rglob("*.py") if "__pycache__" not in p.parts)


def _rel(path: Path) -> str:
    return path.relative_to(BACKEND).as_posix()


def _assigns_attribute(tree: ast.AST, attribute: str) -> bool:
    """Whether the module assigns ``<anything>.<attribute>`` — plain, augmented or annotated."""
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AugAssign | ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Attribute) and target.attr == attribute:
                return True
    return False


def _modules_assigning_attribute(attribute: str, *, exclude: set[str]) -> list[str]:
    offenders = []
    for path in _python_files():
        rel = _rel(path)
        if rel in exclude:
            continue
        if _assigns_attribute(ast.parse(path.read_text()), attribute):
            offenders.append(rel)
    return offenders


def test_only_rollup_module_assigns_report_overall_grade() -> None:
    offenders = _modules_assigning_attribute("overall_grade", exclude={ROLLUP})
    assert offenders == [], f"A7 sole-writer contract violated by: {offenders}"


def test_only_rollup_module_assigns_evaluation_overall_grade() -> None:
    # Same attribute name on a different model — one guard covers both, which is the point:
    # no route may set a grade on either object.
    offenders = _modules_assigning_attribute("overall_grade", exclude={ROLLUP})
    assert offenders == [], f"A7 sole-writer contract violated by: {offenders}"


def test_only_rollup_module_assigns_report_grade_version() -> None:
    offenders = _modules_assigning_attribute("grade_version", exclude={ROLLUP})
    assert offenders == [], f"D3 sole-incrementer contract violated by: {offenders}"


def test_only_rollup_module_assigns_overall_grade_is_manual() -> None:
    # The suppression flag decides whether the computed grade is written at all, so letting a
    # route set it directly would route around the sole writer.
    offenders = _modules_assigning_attribute("overall_grade_is_manual", exclude={ROLLUP})
    assert offenders == [], f"M9 sole-writer contract violated by: {offenders}"


def test_grade_version_is_incremented_in_exactly_one_place() -> None:
    """D3 depends on the counter only ever going up by one, from a single site.

    Two increment sites is how a version gets skipped or reused, and a consumer that uses the
    version to detect a superseded grade then silently keeps a stale number.
    """
    source = (BACKEND / ROLLUP).read_text()
    sites = [line.strip() for line in source.splitlines() if "grade_version" in line and "+ 1" in line]
    assert len(sites) == 1, f"expected one increment site, found {len(sites)}: {sites}"


def test_rollup_module_never_calls_session_commit() -> None:
    """The transaction boundary belongs to ``get_db``, as with record_audit and state_machine.

    A commit inside the rollup would break the atomicity Task 8 relies on: a grade write and
    its rollup must roll back together.
    """
    tree = ast.parse((BACKEND / ROLLUP).read_text())
    commits = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "commit"
    ]
    assert commits == [], f"rollup.py calls commit() at line(s) {[c.lineno for c in commits]}"


def test_the_guard_would_actually_catch_an_offender() -> None:
    """Guard the guard: prove _assigns_attribute detects a real assignment and ignores prose."""
    offending = ast.parse("def f(report):\n    report.overall_grade = 5\n")
    docstring_only = ast.parse('"""Sets report.overall_grade eventually."""\nx = 1\n')
    comparison_only = ast.parse("def f(report):\n    return report.overall_grade == 5\n")
    assert _assigns_attribute(offending, "overall_grade") is True
    assert _assigns_attribute(docstring_only, "overall_grade") is False
    assert _assigns_attribute(comparison_only, "overall_grade") is False
