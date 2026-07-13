"""Demo-data seed for manual exploration of the app.

Run INSIDE the backend container (where ``deploy/.env`` is already loaded and the
``postgres`` hostname resolves on the compose network)::

    docker compose -f deploy/docker-compose.yml exec -T backend \
        uv run --no-sync python -m app.seed_demo

Idempotent: every entity is looked up by its natural key before insert, so
re-running never creates duplicates. It seeds:

* the 5 built-in system roles (reuses ``app.seed.seed_system_roles``);
* a global-admin user whose identity matches the emergency-login subject
  (``emergency:admin``), so the account you log in with already owns the data;
* four extra users (writer / approver / evaluator / observer personas);
* one active exercise with the default team-type set + scoring config
  (reuses ``app.seed.seed_exercise_defaults``);
* two teams (Blue, Red) with members;
* per-user exercise-role assignments;
* one *published* ``sitrep`` template with three sections
  (rich-text, single-choice, numeric-graded).

Log in through the emergency admin using the password whose bcrypt hash is in
``EMERGENCY_ADMIN_PASSWORD_HASH`` (``deploy/.env``).
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
from app.models.exercise_role import ExerciseRole
from app.models.report_template import ReportTemplate
from app.models.team import Team
from app.models.team_member import TeamMember
from app.models.template_section_def import TemplateSectionDef
from app.models.user import User
from app.seed import seed_exercise_defaults, seed_system_roles

# --- user personas (external_id is namespaced "{provider}:{subject}") ---------
# The admin mirrors emergency_claims() (provider="emergency", subject="admin")
# so start_session()'s upsert on emergency-login reuses this very row.
ADMIN_EXTERNAL_ID = "emergency:admin"


@dataclass(frozen=True)
class _Persona:
    external_id: str
    email: str
    display_name: str
    is_global_admin: bool
    role_key: str  # exercise-scoped role assigned below


PERSONAS: tuple[_Persona, ...] = (
    _Persona(ADMIN_EXTERNAL_ID, "admin@localhost", "Emergency Admin", True, "team_admin"),
    _Persona("seed:alice", "alice@range42.local", "Alice Writer", False, "team_writer"),
    _Persona("seed:bob", "bob@range42.local", "Bob Approver", False, "team_approver"),
    _Persona("seed:carol", "carol@range42.local", "Carol Evaluator", False, "evaluator"),
    _Persona("seed:dave", "dave@range42.local", "Dave Observer", False, "observer"),
)

EXERCISE_NAME = "Autumn Cyber Range 2026"
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


async def _ensure_team_member(session: AsyncSession, *, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
    exists = (
        await session.execute(select(TeamMember.id).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id))
    ).first()
    if exists is None:
        session.add(TeamMember(team_id=team_id, user_id=user_id))


async def _ensure_exercise_role(
    session: AsyncSession, *, exercise_id: uuid.UUID, user_id: uuid.UUID, role_key: str
) -> None:
    exists = (
        await session.execute(
            select(ExerciseRole.id).where(
                ExerciseRole.exercise_id == exercise_id,
                ExerciseRole.user_id == user_id,
                ExerciseRole.role_key == role_key,
            )
        )
    ).first()
    if exists is None:
        session.add(ExerciseRole(exercise_id=exercise_id, user_id=user_id, role_key=role_key))


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

    users = {p.external_id: await _get_or_create_user(session, p) for p in PERSONAS}
    admin = users[ADMIN_EXTERNAL_ID]

    exercise = await _get_or_create_exercise(session, created_by=admin.id)
    await seed_exercise_defaults(session, exercise.id)

    blue = await _get_or_create_team(
        session, exercise_id=exercise.id, name="Blue Team Alpha", team_type="blue", color="#3B82F6"
    )
    red = await _get_or_create_team(
        session, exercise_id=exercise.id, name="Red Team Bravo", team_type="red", color="#EF4444"
    )

    await _ensure_team_member(session, team_id=blue.id, user_id=users["seed:alice"].id)
    await _ensure_team_member(session, team_id=blue.id, user_id=users["seed:bob"].id)
    await _ensure_team_member(session, team_id=red.id, user_id=users["seed:dave"].id)

    for p in PERSONAS:
        await _ensure_exercise_role(
            session, exercise_id=exercise.id, user_id=users[p.external_id].id, role_key=p.role_key
        )

    template, template_created = await _get_or_create_template(session, created_by=admin.id)

    return {
        "users": len(users),
        "exercise": exercise.name,
        "teams": [blue.name, red.name],
        "roles_assigned": len(PERSONAS),
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
    print(f"  users            : {summary['users']}")
    print(f"  exercise         : {summary['exercise']} (+ default team-types & scoring)")
    print(f"  teams            : {', '.join(summary['teams'])}")
    print(f"  exercise roles   : {summary['roles_assigned']}")
    print(
        f"  template         : {summary['template']} "
        f"({'created' if summary['template_created'] else 'already present'})"
    )
    print("  log in as        : emergency admin (POST /api/v1/auth/emergency-login)")


if __name__ == "__main__":
    asyncio.run(_main())
