import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class MetadataMixin:
    # stored column name "metadata" (attr suffixed to avoid SQLAlchemy reserved name)
    #
    # USAGE (WP6): apply this mixin to the integration tables too — `api_key` and
    # `webhook_config` both need the metadata-JSONB column (operator-supplied tags,
    # provenance, etc.), so they must inherit MetadataMixin like every domain table.
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, key="metadata_", nullable=True)
