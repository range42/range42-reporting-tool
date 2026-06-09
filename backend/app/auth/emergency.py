"""Emergency local-admin path (OIDC-downtime backstop, ARCHITECTURE §5.1.1).

A single account whose bcrypt hash lives in ``EMERGENCY_ADMIN_PASSWORD_HASH``.
Produces the same ``NormalizedClaims`` shape every other adapter does, with a
constant ``provider="emergency"`` subject so ``upsert_user`` namespaces it to
``emergency:admin``. The login route sets ``is_global_admin=True`` on the row.

Uses the ``bcrypt`` library directly (passlib 1.7.4 is incompatible with
bcrypt 5.x which removed ``bcrypt.__about__``).
"""

import bcrypt as _bcrypt

from app.auth.base import NormalizedClaims

EMERGENCY_SUBJECT = "admin"


def verify_emergency_password(password: str, password_hash: str) -> bool:
    """Constant-time bcrypt check. Returns ``False`` for an empty/invalid hash."""
    if not password_hash:
        return False
    try:
        return _bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError, TypeError:
        return False


def emergency_claims() -> NormalizedClaims:
    """Synthetic claims for the emergency admin (no external IdP involved)."""
    return NormalizedClaims(
        subject=EMERGENCY_SUBJECT,
        email="admin@localhost",
        display_name="Emergency Admin",
        provider="emergency",
        avatar_url=None,
    )
