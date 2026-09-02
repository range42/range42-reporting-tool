import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import client_ip, record_audit
from app.core.db import get_db
from app.core.pagination import PageParams, page_params
from app.core.permissions import (
    REPORTS_APPROVE,
    REPORTS_READ_ALL,
    REPORTS_READ_OWN,
    REPORTS_RECALL,
    REPORTS_SUBMIT,
    REPORTS_WRITE,
    SCORING_READ_ALL,
)
from app.core.rbac import get_current_user, require_global_admin, require_permission, require_permission_any
from app.core.sanitize import html_to_plain, sanitize_html
from app.models import (
    ApprovalRecord,
    Evaluation,
    Report,
    ReportSection,
    ReportTemplate,
    ScoringConfig,
    Team,
    TeamMember,
    TemplateSectionDef,
    User,
)
from app.models.exercise_role import ExerciseRole
from app.models.role_definition import RoleDefinition
from app.schemas.common import DataEnvelope, Page
from app.schemas.report import (
    KNOWN_REPORT_STATUSES,
    ApproveRequest,
    RecallRequest,
    RejectRequest,
    ReportCreate,
    ReportDetailOut,
    ReportOut,
    ReportSectionOut,
    ReportUpdate,
    SectionAnswerUpdate,
)
from app.services.workflow import state_machine

router = APIRouter(tags=["reports"])


# --- shared helpers (reused by all report endpoints) -----------------------


async def _get_report(db: AsyncSession, exercise_id: uuid.UUID, rid: uuid.UUID) -> Report:
    r = (
        await db.execute(select(Report).where(Report.id == rid, Report.exercise_id == exercise_id))
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="report not found")
    return r


async def _section_pairs(db: AsyncSession, report_id: uuid.UUID) -> list[tuple[ReportSection, TemplateSectionDef]]:
    rows = (
        await db.execute(
            select(ReportSection, TemplateSectionDef)
            .join(TemplateSectionDef, TemplateSectionDef.id == ReportSection.section_def_id)
            .where(ReportSection.report_id == report_id)
            .order_by(ReportSection.position)
        )
    ).all()
    return [(s, d) for s, d in rows]


async def _section_count(db: AsyncSession, report_id: uuid.UUID) -> int:
    return (
        await db.execute(select(func.count()).select_from(ReportSection).where(ReportSection.report_id == report_id))
    ).scalar_one()


async def _caller_team_ids(db: AsyncSession, exercise_id: uuid.UUID, user: User) -> set[uuid.UUID]:
    rows = (
        (
            await db.execute(
                select(TeamMember.team_id)
                .join(Team, Team.id == TeamMember.team_id)
                .where(Team.exercise_id == exercise_id, TeamMember.user_id == user.id)
            )
        )
        .scalars()
        .all()
    )
    return set(rows)


async def _has_permission(db: AsyncSession, exercise_id: uuid.UUID, user: User, perm: str) -> bool:
    """Inline permission probe (mirrors require_permission's resolver) for list-filtering decisions."""
    if user.is_global_admin:
        return True
    keys = (
        (
            await db.execute(
                select(ExerciseRole.role_key).where(
                    ExerciseRole.exercise_id == exercise_id, ExerciseRole.user_id == user.id
                )
            )
        )
        .scalars()
        .all()
    )
    if not keys:
        return False
    granted = (
        (await db.execute(select(RoleDefinition.permissions).where(RoleDefinition.role_key.in_(keys)))).scalars().all()
    )
    return any(perm in perms for perms in granted)


async def _assert_report_access(
    db: AsyncSession, exercise_id: uuid.UUID, report: Report, user: User, *, write: bool
) -> None:
    if user.is_global_admin:
        return
    team_ids = await _caller_team_ids(db, exercise_id, user)
    if report.team_id in team_ids:
        return
    if not write and await _has_permission(db, exercise_id, user, REPORTS_READ_ALL):
        return
    raise HTTPException(status_code=403, detail="insufficient permissions")


class _GradeGate:
    """M17 — decides, per report, whether the caller may see the report-level grade.

    The caller-level facts (Global Admin, ``scoring:read:all``, the exercise's
    ``teams_see_own_scores``) are resolved ONCE per request; ``allows`` then costs nothing per
    row, so the list route stays free of an N+1 over the page.

    Rule: Global Admin and ``scoring:read:all`` holders always see it. A team member sees it
    only once the report is ``evaluated`` AND ``teams_see_own_scores`` is true — before that
    a half-graded number would be published to the team being graded. Anyone else (a caller
    with ``reports:read:all`` but no scoring read, should such a role ever exist) sees nothing.
    """

    def __init__(self, *, reads_all_scores: bool, teams_see_own_scores: bool) -> None:
        self._reads_all_scores = reads_all_scores
        self._teams_see_own_scores = teams_see_own_scores

    @classmethod
    async def resolve(cls, db: AsyncSession, exercise_id: uuid.UUID, user: User) -> _GradeGate:
        reads_all = user.is_global_admin or await _has_permission(db, exercise_id, user, SCORING_READ_ALL)
        teams_see = (
            await db.execute(select(ScoringConfig.teams_see_own_scores).where(ScoringConfig.exercise_id == exercise_id))
        ).scalar_one_or_none()
        return cls(reads_all_scores=reads_all, teams_see_own_scores=bool(teams_see))

    def allows(self, report: Report, *, is_team_member: bool) -> bool:
        if self._reads_all_scores:
            return True
        return is_team_member and report.status == "evaluated" and self._teams_see_own_scores


async def _assert_section_write_access(db: AsyncSession, exercise_id: uuid.UUID, report: Report, user: User) -> None:
    """L7 write-lock: an assigned report's sections are editable only by the assigned
    writer, a team admin (holder of ``reports:recall``), or a global admin.

    Layered on top of ``_assert_report_access`` (team scoping); unassigned reports
    keep the team-scoped policy. Applied only to section saves — report metadata
    keeps its existing policy.
    """
    if user.is_global_admin:
        return
    if report.assigned_writer_id is None or report.assigned_writer_id == user.id:
        return
    if await _has_permission(db, exercise_id, user, REPORTS_RECALL):
        return
    raise HTTPException(status_code=403, detail="report is assigned to another writer")


def _require_draft(r: Report) -> None:
    if r.status != "draft":
        raise HTTPException(status_code=409, detail="report is not a draft")


async def _apply_transition(
    db: AsyncSession,
    report: Report,
    *,
    target_status: str,
    actor_id: uuid.UUID,
    action: str,
    details: dict[str, object] | None = None,
    ip: str | None = None,
) -> None:
    """Route through the workflow state machine, mapping a rejected transition to 409."""
    try:
        await state_machine.transition(
            db, report, target_status=target_status, actor_id=actor_id, action=action, details=details, ip=ip
        )
    except state_machine.InvalidTransition as exc:
        raise HTTPException(
            status_code=409, detail={"error": "invalid_state", "from": exc.current, "to": exc.target}
        ) from exc


def _require_status(r: Report, expected: str) -> None:
    if r.status != expected:
        raise HTTPException(status_code=409, detail={"error": "invalid_state", "from": r.status, "to": expected})


async def _approval_records(db: AsyncSession, report_id: uuid.UUID) -> list[ApprovalRecord]:
    return list(
        (
            await db.execute(
                select(ApprovalRecord).where(ApprovalRecord.report_id == report_id).order_by(ApprovalRecord.created_at)
            )
        )
        .scalars()
        .all()
    )


def _chain_entries(report: Report) -> list[dict[str, object]]:
    """The approval chain as an ordered list; empty = single-step default (step 1)."""
    return report.approval_chain or []


def _required_steps(entries: list[dict[str, object]]) -> set[int]:
    """1-based indices of the steps that must be approved to finalize.

    No chain (single-step default) -> {1}. With a chain, the steps whose
    ``required`` flag is true (defaulting to true when omitted).
    """
    if not entries:
        return {1}
    return {i + 1 for i, e in enumerate(entries) if e.get("required", True)}


async def _approved_steps(db: AsyncSession, report_id: uuid.UUID) -> set[int]:
    rows = (
        await db.execute(
            select(ApprovalRecord.step).where(
                ApprovalRecord.report_id == report_id, ApprovalRecord.action == "approved"
            )
        )
    ).scalars()
    return set(rows)


async def _caller_role_keys(db: AsyncSession, exercise_id: uuid.UUID, user: User) -> set[str]:
    rows = (
        await db.execute(
            select(ExerciseRole.role_key).where(
                ExerciseRole.exercise_id == exercise_id, ExerciseRole.user_id == user.id
            )
        )
    ).scalars()
    return set(rows)


async def _is_eligible_for_step(
    db: AsyncSession,
    exercise_id: uuid.UUID,
    user: User,
    entries: list[dict[str, object]],
    step: int,
) -> bool:
    """Whether the caller matches the step's subject (role_key or user_id). Admins bypass.

    A single-step default (no chain) is already gated by the endpoint permission.
    """
    if user.is_global_admin or not entries:
        return True
    entry = entries[step - 1]
    uid = entry.get("user_id")
    if uid is not None:
        return str(user.id) == uid
    role_key = entry.get("role_key")
    return role_key is not None and role_key in await _caller_role_keys(db, exercise_id, user)


async def _assert_step_eligibility(
    db: AsyncSession,
    exercise_id: uuid.UUID,
    user: User,
    entries: list[dict[str, object]],
    step: int,
) -> None:
    """Raise 403 unless the caller is eligible for ``step`` (see _is_eligible_for_step)."""
    if not await _is_eligible_for_step(db, exercise_id, user, entries, step):
        raise HTTPException(status_code=403, detail={"error": "not_eligible_for_step", "step": step})


async def _can_approve(
    db: AsyncSession,
    exercise_id: uuid.UUID,
    report: Report,
    user: User,
    approved: set[int],
) -> bool:
    """Whether ``user`` may approve ``report`` at its current step right now.

    True iff the report is ``pending_approval`` and the caller is eligible for the
    current (smallest unfinished required) step — holding ``reports:approve`` and,
    for a chain, matching that step's subject — or is a global admin. False once the
    caller has already approved the current step.
    """
    if report.status != "pending_approval":
        return False
    if user.is_global_admin:
        return True
    if not await _has_permission(db, exercise_id, user, REPORTS_APPROVE):
        return False
    entries = _chain_entries(report)
    remaining = sorted(_required_steps(entries) - approved)
    step = remaining[0] if remaining else 1
    if step in approved:
        return False
    return await _is_eligible_for_step(db, exercise_id, user, entries, step)


async def _resolve_on_behalf_of(
    db: AsyncSession,
    on_behalf_of: str | None,
    actor: User,
) -> tuple[uuid.UUID, bool]:
    """Resolve the approver identity for an approve action.

    Without ``on_behalf_of`` the actor approves as themselves. With it, only a
    global admin may record the approval on behalf of another (existing) user —
    an audited admin override for a stalled chain (W4-8). Returns
    ``(approver_id, is_admin_override)``.
    """
    if on_behalf_of is None:
        return actor.id, False
    if not actor.is_global_admin:
        raise HTTPException(status_code=403, detail={"error": "not_global_admin"})
    try:
        target_id = uuid.UUID(on_behalf_of)
    except ValueError:
        raise HTTPException(status_code=422, detail={"error": "invalid_on_behalf_of"}) from None
    exists = (await db.execute(select(User.id).where(User.id == target_id))).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=404, detail={"error": "user_not_found", "user_id": on_behalf_of})
    return target_id, True


async def _get_report_section(db: AsyncSession, report_id: uuid.UUID, sid: uuid.UUID) -> ReportSection:
    s = (
        await db.execute(select(ReportSection).where(ReportSection.id == sid, ReportSection.report_id == report_id))
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(status_code=404, detail="section not found")
    return s


# --- instantiate -----------------------------------------------------------


@router.post("/exercises/{exercise_id}/reports", status_code=201)
async def create_report(
    request: Request,
    exercise_id: uuid.UUID,
    body: ReportCreate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[ReportDetailOut]:
    team = (await db.execute(select(Team).where(Team.id == uuid.UUID(body.team_id)))).scalar_one_or_none()
    if team is None:
        raise HTTPException(status_code=404, detail="team not found")
    if team.exercise_id != exercise_id:
        raise HTTPException(status_code=422, detail="team does not belong to this exercise")

    template = (
        await db.execute(select(ReportTemplate).where(ReportTemplate.id == uuid.UUID(body.template_id)))
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="template not found")
    if template.status != "published":
        raise HTTPException(status_code=409, detail="template is not published")

    if body.assigned_writer_id is not None:
        member = (
            await db.execute(
                select(TeamMember.id).where(
                    TeamMember.team_id == team.id, TeamMember.user_id == uuid.UUID(body.assigned_writer_id)
                )
            )
        ).first()
        if member is None:
            raise HTTPException(status_code=422, detail="assigned writer is not a member of the team")

    report = Report(
        exercise_id=exercise_id,
        team_id=team.id,
        template_id=template.id,
        template_version_at_creation=template.version,
        name=body.name,
        description=body.description,
        status="draft",
        approval_required=body.approval_required,
        approval_chain=[e.model_dump() for e in body.approval_chain] if body.approval_chain else None,
        due_at=body.due_at,
        assigned_writer_id=uuid.UUID(body.assigned_writer_id) if body.assigned_writer_id else None,
        created_by=actor.id,
    )
    db.add(report)
    await db.flush()

    defs = (
        (
            await db.execute(
                select(TemplateSectionDef)
                .where(TemplateSectionDef.template_id == template.id)
                .order_by(TemplateSectionDef.position)
            )
        )
        .scalars()
        .all()
    )
    for d in defs:
        db.add(ReportSection(report_id=report.id, section_def_id=d.id, position=d.position, version=1, char_count=0))
    await db.flush()

    await record_audit(
        db,
        user_id=actor.id,
        action="report.create",
        resource_type="report",
        resource_id=report.id,
        details={"template_id": str(template.id), "team_id": str(team.id), "sections": len(defs)},
        ip=client_ip(request),
    )
    return DataEnvelope(data=ReportDetailOut.from_models(report, await _section_pairs(db, report.id)))


# --- list + detail ---------------------------------------------------------


@router.get("/exercises/{exercise_id}/reports")
async def list_reports(
    exercise_id: uuid.UUID,
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission_any([REPORTS_READ_OWN, REPORTS_READ_ALL])),
    db: AsyncSession = Depends(get_db),
    pp: PageParams = Depends(page_params),
    team_id: uuid.UUID | None = None,
    status: str | None = None,
) -> DataEnvelope[list[ReportOut]]:
    if status is not None and status not in KNOWN_REPORT_STATUSES:
        raise HTTPException(status_code=422, detail={"error": "invalid_status"})
    filt = [Report.exercise_id == exercise_id]
    if team_id is not None:
        filt.append(Report.team_id == team_id)
    if status is not None:
        filt.append(Report.status == status)
    # team scoping unless caller can read all (or is admin)
    team_ids = await _caller_team_ids(db, exercise_id, user)
    if not (user.is_global_admin or await _has_permission(db, exercise_id, user, REPORTS_READ_ALL)):
        if not team_ids:
            return DataEnvelope(data=[], meta=Page(page=pp.page, per_page=pp.per_page, total=0))
        filt.append(Report.team_id.in_(team_ids))
    grade_gate = await _GradeGate.resolve(db, exercise_id, user)

    base = select(Report).where(*filt)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(base.order_by(Report.created_at.desc()).offset(pp.offset).limit(pp.limit))).scalars().all()
    counts = {
        rid: cnt
        for rid, cnt in (
            await db.execute(
                select(ReportSection.report_id, func.count())
                .where(ReportSection.report_id.in_([r.id for r in rows]))
                .group_by(ReportSection.report_id)
            )
        ).all()
    }
    # can_approve is only ever true for pending_approval reports; batch their
    # approved-step sets in one query to avoid an N+1 over the page.
    pending_ids = [r.id for r in rows if r.status == "pending_approval"]
    approved_by_report: dict[uuid.UUID, set[int]] = {}
    if pending_ids:
        for report_id, step in (
            await db.execute(
                select(ApprovalRecord.report_id, ApprovalRecord.step).where(
                    ApprovalRecord.report_id.in_(pending_ids), ApprovalRecord.action == "approved"
                )
            )
        ).all():
            approved_by_report.setdefault(report_id, set()).add(step)
    data = [
        ReportOut.from_model(
            r,
            counts.get(r.id, 0),
            can_approve=await _can_approve(db, exercise_id, r, user, approved_by_report.get(r.id, set())),
            grade_visible=grade_gate.allows(r, is_team_member=r.team_id in team_ids),
        )
        for r in rows
    ]
    return DataEnvelope(
        data=data,
        meta=Page(page=pp.page, per_page=pp.per_page, total=total),
    )


@router.get("/exercises/{exercise_id}/reports/{rid}")
async def get_report(
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission_any([REPORTS_READ_OWN, REPORTS_READ_ALL])),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[ReportDetailOut]:
    report = await _get_report(db, exercise_id, rid)
    await _assert_report_access(db, exercise_id, report, user, write=False)
    approved = await _approved_steps(db, report.id)
    can_approve = await _can_approve(db, exercise_id, report, user, approved)
    grade_gate = await _GradeGate.resolve(db, exercise_id, user)
    is_team_member = report.team_id in await _caller_team_ids(db, exercise_id, user)
    return DataEnvelope(
        data=ReportDetailOut.from_models(
            report,
            await _section_pairs(db, rid),
            await _approval_records(db, rid),
            can_approve=can_approve,
            grade_visible=grade_gate.allows(report, is_team_member=is_team_member),
        )
    )


# --- metadata update + delete (GA, draft-only) -----------------------------


@router.patch("/exercises/{exercise_id}/reports/{rid}")
async def update_report(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    body: ReportUpdate,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[ReportOut]:
    report = await _get_report(db, exercise_id, rid)
    _require_draft(report)
    data = body.model_dump(exclude_unset=True)
    changed = sorted(data.keys())
    if "assigned_writer_id" in data and data["assigned_writer_id"] is not None:
        member = (
            await db.execute(
                select(TeamMember.id).where(
                    TeamMember.team_id == report.team_id, TeamMember.user_id == uuid.UUID(data["assigned_writer_id"])
                )
            )
        ).first()
        if member is None:
            raise HTTPException(status_code=422, detail="assigned writer is not a member of the team")
        data["assigned_writer_id"] = uuid.UUID(data["assigned_writer_id"])
    for k, v in data.items():
        setattr(report, k, v)
    await db.flush()
    await db.refresh(report)
    await record_audit(
        db,
        user_id=actor.id,
        action="report.update",
        resource_type="report",
        resource_id=report.id,
        details={"changed": changed},
        ip=client_ip(request),
    )
    return DataEnvelope(data=ReportOut.from_model(report, await _section_count(db, rid)))


@router.delete("/exercises/{exercise_id}/reports/{rid}", status_code=204)
async def delete_report(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    actor: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    report = await _get_report(db, exercise_id, rid)
    _require_draft(report)
    await db.delete(report)
    await db.flush()
    await record_audit(
        db,
        user_id=actor.id,
        action="report.delete",
        resource_type="report",
        resource_id=rid,
        details=None,
        ip=client_ip(request),
    )


# --- section save (sanitize + optimistic concurrency + validation) ---------


@router.patch("/exercises/{exercise_id}/reports/{rid}/sections/{sid}")
async def save_section(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    sid: uuid.UUID,
    body: SectionAnswerUpdate,
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission(REPORTS_WRITE)),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[ReportSectionOut]:
    report = await _get_report(db, exercise_id, rid)
    _require_draft(report)
    await _assert_report_access(db, exercise_id, report, user, write=True)
    await _assert_section_write_access(db, exercise_id, report, user)
    section = await _get_report_section(db, rid, sid)
    section_def = (
        await db.execute(select(TemplateSectionDef).where(TemplateSectionDef.id == section.section_def_id))
    ).scalar_one()

    if body.version != section.version:
        # 409 carries the current section state so the client can resolve the conflict (spec §6.1)
        raise HTTPException(
            status_code=409,
            detail={
                "error": "stale_version",
                "section": ReportSectionOut.from_models(section, section_def).model_dump(mode="json"),
            },
        )
    section_body = body.body  # narrow the discriminated union via a local (mypy-safe)
    if section_body.kind != section_def.field_type:
        raise HTTPException(status_code=422, detail="field_type_mismatch")

    if section_body.kind == "rich_text":
        clean = sanitize_html(section_body.content)
        plain = html_to_plain(section_body.content)
        if section_def.char_limit is not None and len(plain) > section_def.char_limit:
            raise HTTPException(status_code=422, detail="content exceeds char_limit")
        section.content = clean
        section.content_plain = plain
        section.char_count = len(plain)
        section.choice_values = None
    else:  # choice
        cfg = section_def.choice_config or {}
        valid = {v["code"] for v in cfg.get("values", []) if not v.get("deprecated_at")}
        codes = section_body.choice_values
        if any(code not in valid for code in codes):
            raise HTTPException(status_code=422, detail="unknown choice code")
        if cfg.get("selection") == "single" and len(codes) > 1:
            raise HTTPException(status_code=422, detail="single-selection allows at most one value")
        if len(set(codes)) != len(codes):
            raise HTTPException(status_code=422, detail="duplicate choice codes")
        section.choice_values = codes
        section.content = None
        section.content_plain = None
        section.char_count = 0

    section.version += 1
    section.last_edited_by = user.id
    section.last_edited_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(section)
    await record_audit(
        db,
        user_id=user.id,
        action="report_section.update",
        resource_type="report_section",
        resource_id=section.id,
        details={"report_id": str(rid)},
        ip=client_ip(request),
    )
    return DataEnvelope(data=ReportSectionOut.from_models(section, section_def))


# --- submit (draft -> submitted, required-empty gate) ----------------------


@router.post("/exercises/{exercise_id}/reports/{rid}/submit")
async def submit_report(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission(REPORTS_SUBMIT)),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[ReportDetailOut]:
    report = await _get_report(db, exercise_id, rid)
    _require_draft(report)
    await _assert_report_access(db, exercise_id, report, user, write=True)

    pairs = await _section_pairs(db, rid)
    missing: list[str] = []
    for section, d in pairs:
        if not d.is_required:
            continue
        if d.field_type == "rich_text":
            if section.char_count == 0:
                missing.append(str(d.id))
        elif not section.choice_values:
            missing.append(str(d.id))
    if missing:
        raise HTTPException(status_code=409, detail={"error": "required_section_empty", "section_def_ids": missing})

    # approval_required routes to pending_approval; otherwise straight to submitted.
    # The state machine is the sole writer of report.status + submitted_at + audit.
    target = "pending_approval" if report.approval_required else "submitted"
    await _apply_transition(
        db, report, target_status=target, actor_id=user.id, action="report.submit", ip=client_ip(request)
    )
    await db.refresh(report)
    return DataEnvelope(data=ReportDetailOut.from_models(report, await _section_pairs(db, rid)))


# --- approval: approve / reject --------------------------------------------
# Authorized on the reports:approve permission alone (exercise-scoped) — an
# approver need not be a member of the report's team. A report stays in
# pending_approval until all *required* chain steps are approved, then the state
# machine finalizes it to submitted. No chain (or a single entry) = single step 1.


@router.post("/exercises/{exercise_id}/reports/{rid}/approve")
async def approve_report(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    body: ApproveRequest | None = None,
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission(REPORTS_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[ReportDetailOut]:
    body = body or ApproveRequest()
    report = await _get_report(db, exercise_id, rid)
    _require_status(report, "pending_approval")

    entries = _chain_entries(report)
    n_steps = len(entries) or 1
    required = _required_steps(entries)
    approved = await _approved_steps(db, report.id)

    if body.step is not None:
        if not (1 <= body.step <= n_steps):
            raise HTTPException(status_code=422, detail={"error": "invalid_step", "step": body.step})
        step = body.step
    else:
        remaining = sorted(required - approved)
        step = remaining[0] if remaining else 1
    if step in approved:
        raise HTTPException(status_code=409, detail={"error": "step_already_approved", "step": step})

    approver_id, is_admin_override = await _resolve_on_behalf_of(db, body.on_behalf_of, user)
    if not is_admin_override:
        await _assert_step_eligibility(db, exercise_id, user, entries, step)

    db.add(
        ApprovalRecord(
            report_id=report.id,
            approver_id=approver_id,
            step=step,
            action="approved",
            is_admin_override=is_admin_override,
            comment=body.comment,
        )
    )
    await db.flush()

    approved = approved | {step}
    if required <= approved:
        await _apply_transition(
            db,
            report,
            target_status="submitted",
            actor_id=user.id,
            action="report.approve",
            details={"step": step, "is_admin_override": is_admin_override},
            ip=client_ip(request),
        )
    else:
        # mid-chain approval: one audit row, no status change.
        await record_audit(
            db,
            user_id=user.id,
            action="report.approve",
            resource_type="report",
            resource_id=report.id,
            details={"step": step, "remaining": sorted(required - approved), "is_admin_override": is_admin_override},
            ip=client_ip(request),
        )
    await db.refresh(report)
    return DataEnvelope(
        data=ReportDetailOut.from_models(report, await _section_pairs(db, rid), await _approval_records(db, rid))
    )


@router.post("/exercises/{exercise_id}/reports/{rid}/reject")
async def reject_report(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    body: RejectRequest,
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission(REPORTS_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[ReportDetailOut]:
    report = await _get_report(db, exercise_id, rid)
    _require_status(report, "pending_approval")
    db.add(
        ApprovalRecord(
            report_id=report.id,
            approver_id=user.id,
            step=body.step or 1,
            action="rejected",
            is_admin_override=False,
            comment=body.comment,
        )
    )
    await db.flush()
    await _apply_transition(
        db,
        report,
        target_status="draft",
        actor_id=user.id,
        action="report.reject",
        details={"comment": body.comment},
        ip=client_ip(request),
    )
    await db.refresh(report)
    return DataEnvelope(
        data=ReportDetailOut.from_models(report, await _section_pairs(db, rid), await _approval_records(db, rid))
    )


async def _evaluation_started(db: AsyncSession, report: Report) -> bool:
    """Whether evaluation of ``report`` has begun — recall is blocked once it has (§7.2).

    'Begun' means at least one evaluation is ``in_progress`` or ``completed``. A merely
    ``assigned`` evaluator does NOT block recall: assignment is not the start of work.
    """
    n = (
        await db.execute(
            select(func.count())
            .select_from(Evaluation)
            .where(Evaluation.report_id == report.id, Evaluation.status.in_(("in_progress", "completed")))
        )
    ).scalar_one()
    return n > 0


@router.post("/exercises/{exercise_id}/reports/{rid}/recall")
async def recall_report(
    request: Request,
    exercise_id: uuid.UUID,
    rid: uuid.UUID,
    body: RecallRequest | None = None,
    user: User = Depends(get_current_user),
    _: None = Depends(require_permission(REPORTS_RECALL)),
    db: AsyncSession = Depends(get_db),
) -> DataEnvelope[ReportDetailOut]:
    body = body or RecallRequest()
    report = await _get_report(db, exercise_id, rid)
    _require_status(report, "submitted")
    if await _evaluation_started(db, report):
        raise HTTPException(status_code=409, detail={"error": "evaluation_in_progress"})
    # Recall is not an approval action -> no approval_record, just the state transition.
    await _apply_transition(
        db,
        report,
        target_status="draft",
        actor_id=user.id,
        action="report.recall",
        details={"comment": body.comment},
        ip=client_ip(request),
    )
    await db.refresh(report)
    return DataEnvelope(
        data=ReportDetailOut.from_models(report, await _section_pairs(db, rid), await _approval_records(db, rid))
    )
