from app.models.audit import AuditLog
from app.models.user import User
from app.models.user_session import UserSession


def test_user_table_and_columns() -> None:
    assert User.__tablename__ == "user"
    cols = User.__table__.columns
    assert {
        "id",
        "external_id",
        "email",
        "display_name",
        "avatar_url",
        "is_global_admin",
        "last_login_at",
        "created_at",
        "updated_at",
    } <= set(cols.keys())
    assert cols["external_id"].unique is True
    assert cols["is_global_admin"].nullable is False


def test_user_session_table_and_pk() -> None:
    assert UserSession.__tablename__ == "user_session"
    cols = UserSession.__table__.columns
    assert {"jti", "user_id", "auth_time", "expires_at", "revoked_at", "last_seen_at", "created_at"} <= set(cols.keys())
    assert cols["jti"].primary_key is True


def test_audit_log_is_append_only_shape() -> None:
    assert AuditLog.__tablename__ == "audit_log"
    cols = AuditLog.__table__.columns
    assert {"id", "user_id", "action", "resource_type", "resource_id", "details", "ip_address", "created_at"} <= set(
        cols.keys()
    )
    # Append-only: no updated_at column (immutable rows).
    assert "updated_at" not in cols
