"""Default report-template bundles, seeded once a global admin exists.

Run INSIDE the backend container, passing an admin's email. ``created_by`` is a
required FK to an existing ``user`` row, so that admin must have already logged in
at least once (emergency login in dev, SSO in prod)::

    docker compose -f deploy/docker-compose.yml exec -T backend \
        uv run --no-sync python -m app.seed_default_templates admin@range42.local

Each fixture under ``app/fixtures/default_templates/*.json`` is a ``TemplateBundle``
(the same schema the admin UI's template export/import uses), so a fixture can be
edited, hand-written, or replaced with an export of an existing template.

Idempotent: templates are looked up by ``(name, report_type)`` before insert, and
are seeded already ``published`` since they ship with a complete section list.
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import build_engine, get_sessionmaker
from app.models.report_template import ReportTemplate
from app.models.template_section_def import TemplateSectionDef
from app.models.user import User
from app.schemas.template import TemplateBundle

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "default_templates"


def _load_bundles() -> list[TemplateBundle]:
    return [TemplateBundle.model_validate(json.loads(path.read_text())) for path in sorted(FIXTURES_DIR.glob("*.json"))]


async def _get_or_create_template(
    session: AsyncSession, bundle: TemplateBundle, *, created_by: uuid.UUID
) -> tuple[ReportTemplate, bool]:
    existing = (
        await session.execute(
            select(ReportTemplate).where(
                ReportTemplate.name == bundle.name, ReportTemplate.report_type == bundle.report_type
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False
    template = ReportTemplate(
        lineage_id=uuid.uuid4(),
        version=1,
        name=bundle.name,
        report_type=bundle.report_type,
        description=bundle.description,
        status="published",
        created_by=created_by,
    )
    session.add(template)
    await session.flush()
    for i, sec in enumerate(bundle.sections):
        session.add(
            TemplateSectionDef(
                template_id=template.id,
                position=i,
                name=sec.name,
                description=sec.description,
                default_content=sec.default_content,
                field_type=sec.field_type,
                char_limit=sec.char_limit,
                is_required=sec.is_required,
                grade_mode=sec.grade_mode,
                grade_min=sec.grade_min,
                grade_max=sec.grade_max,
                grade_weight=sec.grade_weight,
                rubric_criteria=sec.rubric_criteria,
                evaluation_criteria=sec.evaluation_criteria,
                choice_config=sec.choice_config,
                mitre_attack_tags=sec.mitre_attack_tags,
                capec_tags=sec.capec_tags,
                cwe_tags=sec.cwe_tags,
            )
        )
    await session.flush()
    return template, True


async def seed_default_templates(session: AsyncSession, *, created_by: uuid.UUID) -> list[tuple[str, bool]]:
    """Seed each fixture bundle. Returns ``[(template name, created)]`` in fixture order."""
    results = []
    for bundle in _load_bundles():
        template, created = await _get_or_create_template(session, bundle, created_by=created_by)
        results.append((template.name, created))
    return results


async def _main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m app.seed_default_templates <admin-email>")
        raise SystemExit(1)
    email = sys.argv[1]

    settings = get_settings()
    engine = build_engine(settings.database_url)
    sm = get_sessionmaker(engine)
    try:
        async with sm() as session:
            admin = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if admin is None:
                print(f"no user found with email {email!r} — they must log in at least once first")
                raise SystemExit(1)
            if not admin.is_global_admin:
                print(f"user {email!r} is not a global admin")
                raise SystemExit(1)
            results = await seed_default_templates(session, created_by=admin.id)
            await session.commit()
    finally:
        await engine.dispose()

    print("default templates seed complete:")
    for name, created in results:
        print(f"  {name} ({'created' if created else 'already present'})")


if __name__ == "__main__":
    asyncio.run(_main())
