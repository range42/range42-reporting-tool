"""User directory search — Global-Admin only.

Backs the member/writer/role-assignment pickers across the admin UI (WP2 follow-up, #201).
No open browse: an empty or missing ``q`` returns no results, so this can never be used to dump
the whole user table.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.pagination import PageParams, page_params
from app.core.rbac import require_global_admin
from app.models import User
from app.schemas.auth import UserOut
from app.schemas.common import DataEnvelope, Page

router = APIRouter(tags=["users"])


@router.get("/users")
async def search_users(
    q: str = "",
    _: User = Depends(require_global_admin),
    db: AsyncSession = Depends(get_db),
    pp: PageParams = Depends(page_params),
) -> DataEnvelope[list[UserOut]]:
    q = q.strip()
    if not q:
        return DataEnvelope(data=[], meta=Page(page=pp.page, per_page=pp.per_page, total=0))
    pattern = f"%{q}%"
    base = select(User).where(or_(User.display_name.ilike(pattern), User.email.ilike(pattern)))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(base.order_by(User.display_name).offset(pp.offset).limit(pp.limit))).scalars().all()
    return DataEnvelope(
        data=[UserOut.from_model(u) for u in rows],
        meta=Page(page=pp.page, per_page=pp.per_page, total=total),
    )
