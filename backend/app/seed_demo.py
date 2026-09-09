"""Demo-data seed for manual exploration of the app.

Run INSIDE the backend container (where ``deploy/.env`` is already loaded and the
``postgres`` hostname resolves on the compose network)::

    docker compose -f deploy/docker-compose.yml exec -T backend \
        uv run --no-sync python -m app.seed_demo

Seeds the *world* only. Persona users are deliberately absent: their rows are
created by their first SSO login, and ``app.seed_grants`` attaches roles and team
membership afterwards, matched by email. Seeding a persona here would key it to a
subject no login can ever match.

Idempotent: every entity is looked up by its natural key before insert, so
re-running never creates duplicates. It seeds:

* the 5 built-in system roles (reuses ``app.seed.seed_system_roles``);
* a global-admin user matching the emergency-login subject (``emergency:admin``),
  which also owns the seeded data as ``created_by``;
* one active exercise with the default team-type set + scoring config
  (reuses ``app.seed.seed_exercise_defaults``);
* two teams (Blue, Red), without members;
* one *published* ``sitrep`` template with three sections
  (rich-text, single-choice, numeric-graded).

Log in through the emergency admin using the password whose bcrypt hash is in
``EMERGENCY_ADMIN_PASSWORD_HASH`` (``deploy/.env``), or through the IdP and then
run ``app.seed_grants``.
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import build_engine, get_sessionmaker
from app.models.exercise import Exercise
from app.models.report_template import ReportTemplate
from app.models.team import Team
from app.models.template_section_def import TemplateSectionDef
from app.models.user import User
from app.seed import seed_exercise_defaults, seed_system_roles

# --- the emergency admin (external_id is namespaced "{provider}:{subject}") ---
# Mirrors emergency_claims() (provider="emergency", subject="admin") so
# start_session()'s upsert on emergency-login reuses this very row. It needs no
# exercise role: require_permission() lets global admins bypass.
ADMIN_EXTERNAL_ID = "emergency:admin"


@dataclass(frozen=True)
class _Persona:
    external_id: str
    email: str
    display_name: str
    is_global_admin: bool


ADMIN = _Persona(ADMIN_EXTERNAL_ID, "admin@localhost", "Emergency Admin", True)

EXERCISE_NAME = "Autumn Cyber Range 2026"
BLUE_TEAM_NAME = "Blue Team Alpha"
RED_TEAM_NAME = "Red Team Bravo"
TEMPLATE_NAME = "Situation Report (SITREP)"

# Section definitions for the demo template. Each dict is validated against the
# same invariants the API enforces (app.schemas.template.section_invariant_error).
_SECTIONS: tuple[dict[str, Any], ...] = (
    {
        "position": 1,
        "name": "Executive Summary",
        "description": "High-level narrative for leadership.",
        "field_type": "rich_text",
        "char_limit": 2000,
        "is_required": True,
        "grade_mode": "not_graded",
    },
    {
        "position": 2,
        "name": "Incident Severity",
        "description": "Overall severity classification.",
        "field_type": "choice",
        "is_required": True,
        "grade_mode": "not_graded",
        "choice_config": {
            "selection": "single",
            "values": [
                {"code": "low", "label": "Low", "position": 1},
                {"code": "medium", "label": "Medium", "position": 2},
                {"code": "high", "label": "High", "position": 3},
                {"code": "critical", "label": "Critical", "position": 4},
            ],
        },
    },
    {
        "position": 3,
        "name": "Technical Analysis",
        "description": "Detailed technical findings (scored 0-10).",
        "field_type": "rich_text",
        "char_limit": 8000,
        "is_required": True,
        "grade_mode": "numeric",
        "grade_min": 0.0,
        "grade_max": 10.0,
        "grade_weight": 2.0,
        "evaluation_criteria": "Depth of analysis, accuracy of IOCs, clarity of remediation.",
    },
)


async def _get_or_create_user(session: AsyncSession, p: _Persona) -> User:
    user = (await session.execute(select(User).where(User.external_id == p.external_id))).scalar_one_or_none()
    if user is None:
        user = User(
            external_id=p.external_id,
            email=p.email,
            display_name=p.display_name,
            is_global_admin=p.is_global_admin,
        )
        session.add(user)
        await session.flush()
    return user


async def _get_or_create_exercise(session: AsyncSession, *, created_by: uuid.UUID) -> Exercise:
    exercise = (await session.execute(select(Exercise).where(Exercise.name == EXERCISE_NAME))).scalar_one_or_none()
    if exercise is None:
        now = datetime.now(UTC)
        exercise = Exercise(
            name=EXERCISE_NAME,
            description="Seeded demo exercise for manual walkthroughs.",
            status="active",
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=6),
            classification="UNCLASSIFIED",
            tlp="CLEAR",
            created_by=created_by,
        )
        session.add(exercise)
        await session.flush()
    return exercise


async def _get_or_create_team(
    session: AsyncSession, *, exercise_id: uuid.UUID, name: str, team_type: str, color: str
) -> Team:
    team = (
        await session.execute(select(Team).where(Team.exercise_id == exercise_id, Team.name == name))
    ).scalar_one_or_none()
    if team is None:
        team = Team(exercise_id=exercise_id, name=name, team_type=team_type, color=color)
        session.add(team)
        await session.flush()
    return team


async def _get_or_create_template(session: AsyncSession, *, created_by: uuid.UUID) -> tuple[ReportTemplate, bool]:
    template = (
        await session.execute(select(ReportTemplate).where(ReportTemplate.name == TEMPLATE_NAME))
    ).scalar_one_or_none()
    if template is not None:
        return template, False
    template = ReportTemplate(
        lineage_id=uuid.uuid4(),
        version=1,
        name=TEMPLATE_NAME,
        report_type="sitrep",
        description="Seeded demo template with mixed section types.",
        status="published",
        created_by=created_by,
    )
    session.add(template)
    await session.flush()
    for spec in _SECTIONS:
        session.add(
            TemplateSectionDef(
                template_id=template.id,
                position=spec["position"],
                name=spec["name"],
                description=spec.get("description"),
                field_type=spec["field_type"],
                char_limit=spec.get("char_limit"),
                is_required=spec.get("is_required", True),
                grade_mode=spec.get("grade_mode", "not_graded"),
                grade_min=spec.get("grade_min"),
                grade_max=spec.get("grade_max"),
                grade_weight=spec.get("grade_weight", 1.0),
                rubric_criteria=spec.get("rubric_criteria"),
                evaluation_criteria=spec.get("evaluation_criteria"),
                choice_config=spec.get("choice_config"),
                mitre_attack_tags=spec.get("mitre_attack_tags", []),
                capec_tags=spec.get("capec_tags", []),
                cwe_tags=spec.get("cwe_tags", []),
            )
        )
    await session.flush()
    return template, True


async def seed_demo(session: AsyncSession) -> dict[str, Any]:
    """Seed the full demo dataset. Returns a summary dict for logging."""
    await seed_system_roles(session)

    admin = await _get_or_create_user(session, ADMIN)

    exercise = await _get_or_create_exercise(session, created_by=admin.id)
    await seed_exercise_defaults(session, exercise.id)

    blue = await _get_or_create_team(
        session, exercise_id=exercise.id, name=BLUE_TEAM_NAME, team_type="blue", color="#3B82F6"
    )
    red = await _get_or_create_team(
        session, exercise_id=exercise.id, name=RED_TEAM_NAME, team_type="red", color="#EF4444"
    )

    template, template_created = await _get_or_create_template(session, created_by=admin.id)

    return {
        "users": 1,
        "exercise": exercise.name,
        "teams": [blue.name, red.name],
        "template": template.name,
        "template_created": template_created,
        "admin_external_id": ADMIN_EXTERNAL_ID,
    }


async def _main() -> None:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    sm = get_sessionmaker(engine)
    try:
        async with sm() as session:
            summary = await seed_demo(session)
            await session.commit()
    finally:
        await engine.dispose()

    print("demo seed complete:")
    print(f"  users            : {summary['users']} (emergency admin only)")
    print(f"  exercise         : {summary['exercise']} (+ default team-types & scoring)")
    print(f"  teams            : {', '.join(summary['teams'])} (no members yet)")
    print(
        f"  template         : {summary['template']} "
        f"({'created' if summary['template_created'] else 'already present'})"
    )
    print("  log in as        : emergency admin (POST /api/v1/auth/emergency-login)")
    print("  next             : persona SSO logins, then `just seed-grants`")


if __name__ == "__main__":
    asyncio.run(_main())
