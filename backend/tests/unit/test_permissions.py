from app.core.permissions import (
    AUDIT_READ,
    EXERCISES_WRITE,
    PERMISSION_CATALOGUE,
    REPORTS_READ_ALL,
    REPORTS_RECALL,
    SCORING_CONFIG_WRITE,
    SYSTEM_ROLES,
    SYSTEM_ROLES_BY_KEY,
    TEAMS_WRITE,
    TEMPLATES_WRITE,
)

GLOBAL_ONLY = {EXERCISES_WRITE, TEAMS_WRITE, TEMPLATES_WRITE, SCORING_CONFIG_WRITE, AUDIT_READ}


def test_catalogue_has_19_strings() -> None:
    assert len(PERMISSION_CATALOGUE) == 19


def test_five_system_roles_with_expected_keys() -> None:
    assert {r.role_key for r in SYSTEM_ROLES} == {"team_admin", "team_writer", "team_approver", "evaluator", "observer"}
    assert set(SYSTEM_ROLES_BY_KEY) == {r.role_key for r in SYSTEM_ROLES}


def test_every_role_permission_is_in_the_catalogue() -> None:
    for role in SYSTEM_ROLES:
        assert role.permissions <= PERMISSION_CATALOGUE, role.role_key


def test_global_only_strings_in_no_system_role() -> None:
    for role in SYSTEM_ROLES:
        assert not (role.permissions & GLOBAL_ONLY), role.role_key


def test_role_permission_membership_matrix() -> None:
    by = SYSTEM_ROLES_BY_KEY
    assert REPORTS_RECALL in by["team_admin"].permissions
    assert REPORTS_RECALL not in by["team_writer"].permissions
    assert "reports:approve" in by["team_approver"].permissions
    assert "reports:write" not in by["team_approver"].permissions
    assert "evaluations:write" in by["evaluator"].permissions
    assert "reports:read:own" not in by["evaluator"].permissions
    assert REPORTS_READ_ALL in by["observer"].permissions
    assert by["observer"].permissions.isdisjoint(
        {"reports:write", "reports:submit", "reports:approve", "evaluations:write"}
    )
    for role in by.values():
        assert {"exercises:read", "teams:read", "templates:read"} <= role.permissions
