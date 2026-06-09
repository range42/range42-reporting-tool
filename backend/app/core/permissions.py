"""Permission catalogue + built-in role definitions (single source of truth).

The 19 permission strings (ARCHITECTURE §4.2) and the five seeded system roles
(§5.2 matrix). Consumed by the seed (``app.seed``), the ``require_permission``
resolver (``core.rbac``), and later the frontend Roles editor. Global-only strings
(``exercises:write``, ``teams:write``, ``templates:write``, ``scoring:config:write``,
``audit:read``) are granted to Global Admin via ``require_global_admin`` and are
carried by no exercise-scoped system role (design §4.3).
"""

from dataclasses import dataclass

EXERCISES_READ = "exercises:read"
EXERCISES_WRITE = "exercises:write"
TEAMS_READ = "teams:read"
TEAMS_WRITE = "teams:write"
TEMPLATES_READ = "templates:read"
TEMPLATES_WRITE = "templates:write"
REPORTS_READ_OWN = "reports:read:own"
REPORTS_READ_ASSIGNED = "reports:read:assigned"
REPORTS_READ_ALL = "reports:read:all"
REPORTS_WRITE = "reports:write"
REPORTS_SUBMIT = "reports:submit"
REPORTS_APPROVE = "reports:approve"
REPORTS_RECALL = "reports:recall"
EVALUATIONS_WRITE = "evaluations:write"
EVALUATIONS_READ_OWN = "evaluations:read:own"
SCORING_READ_OWN = "scoring:read:own"
SCORING_READ_ALL = "scoring:read:all"
SCORING_CONFIG_WRITE = "scoring:config:write"
AUDIT_READ = "audit:read"

PERMISSION_CATALOGUE: frozenset[str] = frozenset(
    {
        EXERCISES_READ,
        EXERCISES_WRITE,
        TEAMS_READ,
        TEAMS_WRITE,
        TEMPLATES_READ,
        TEMPLATES_WRITE,
        REPORTS_READ_OWN,
        REPORTS_READ_ASSIGNED,
        REPORTS_READ_ALL,
        REPORTS_WRITE,
        REPORTS_SUBMIT,
        REPORTS_APPROVE,
        REPORTS_RECALL,
        EVALUATIONS_WRITE,
        EVALUATIONS_READ_OWN,
        SCORING_READ_OWN,
        SCORING_READ_ALL,
        SCORING_CONFIG_WRITE,
        AUDIT_READ,
    }
)

_COMMON_READ = frozenset({EXERCISES_READ, TEAMS_READ, TEMPLATES_READ})


@dataclass(frozen=True)
class SystemRole:
    """A built-in role seeded into ``role_definition`` (is_system=True)."""

    role_key: str
    display_label: str
    description: str
    permissions: frozenset[str]


SYSTEM_ROLES: tuple[SystemRole, ...] = (
    SystemRole(
        role_key="team_admin",
        display_label="Team Admin",
        description="Blue-team administrator: manage, submit, and recall the team's reports.",
        permissions=_COMMON_READ
        | frozenset(
            {REPORTS_READ_OWN, REPORTS_WRITE, REPORTS_SUBMIT, REPORTS_RECALL, EVALUATIONS_READ_OWN, SCORING_READ_OWN}
        ),
    ),
    SystemRole(
        role_key="team_writer",
        display_label="Team Writer",
        description="Blue-team writer: draft and submit assigned reports.",
        permissions=_COMMON_READ
        | frozenset({REPORTS_READ_OWN, REPORTS_WRITE, REPORTS_SUBMIT, EVALUATIONS_READ_OWN, SCORING_READ_OWN}),
    ),
    SystemRole(
        role_key="team_approver",
        display_label="Team Approver",
        description="Blue-team approver: review and approve/reject the team's reports.",
        permissions=_COMMON_READ
        | frozenset({REPORTS_READ_OWN, REPORTS_APPROVE, EVALUATIONS_READ_OWN, SCORING_READ_OWN}),
    ),
    SystemRole(
        role_key="evaluator",
        display_label="Evaluator",
        description="Evaluates assigned reports and sees all scores.",
        permissions=_COMMON_READ | frozenset({REPORTS_READ_ASSIGNED, EVALUATIONS_WRITE, SCORING_READ_ALL}),
    ),
    SystemRole(
        role_key="observer",
        display_label="Observer",
        description="Read-only access to all reports and scores in the exercise.",
        permissions=_COMMON_READ | frozenset({REPORTS_READ_ALL, SCORING_READ_ALL}),
    ),
)

SYSTEM_ROLES_BY_KEY: dict[str, SystemRole] = {r.role_key: r for r in SYSTEM_ROLES}
