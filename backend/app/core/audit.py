"""Audit-log write path. The audit_log table is append-only (DB trigger); this is the
only place domain mutations record an entry. Call inside a mutating handler so the row
commits atomically with the mutation via get_db's unit-of-work."""

import ipaddress
import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def _valid_ip(ip: str | None) -> str | None:
    if ip is None:
        return None
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return None
    return ip


def client_ip(request: Request) -> str | None:
    """The request's client IP, or None when unavailable (e.g. ASGI test transport)."""
    return request.client.host if request.client else None


async def record_audit(
    session: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Append an audit_log row within the caller's transaction (no commit).

    ``ip`` is validated and dropped to NULL if not a valid IP address.
    """
    session.add(
        AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=_valid_ip(ip),
        )
    )
    await session.flush()
