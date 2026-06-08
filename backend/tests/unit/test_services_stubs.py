import importlib


def test_workflow_state_machine_imports() -> None:
    mod = importlib.import_module("app.services.workflow.state_machine")
    assert hasattr(mod, "transition")


def test_scoring_rollup_imports() -> None:
    mod = importlib.import_module("app.services.scoring.rollup")
    assert hasattr(mod, "rollup")
    assert hasattr(mod, "GradeTimeline")
