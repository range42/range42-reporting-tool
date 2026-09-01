import importlib


def test_workflow_state_machine_imports() -> None:
    mod = importlib.import_module("app.services.workflow.state_machine")
    assert hasattr(mod, "transition")


def test_scoring_rollup_is_implemented() -> None:
    # Replaces the WP1 reservation check: W5-2 filled the module in, so the entry point must
    # exist and must not be the NotImplementedError placeholder any more.
    mod = importlib.import_module("app.services.scoring.rollup")
    assert hasattr(mod, "recompute_report_grade")
    assert hasattr(mod, "GradeTimeline")
    assert not hasattr(mod, "rollup"), "the rollup() shape reservation should be gone"
