import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, MetadataMixin, TimestampMixin, UUIDMixin


class _Sample(UUIDMixin, TimestampMixin, MetadataMixin, Base):
    __tablename__ = "sample"
    name: Mapped[str] = mapped_column(String(50))


def test_uuid_pk_default_callable() -> None:
    col = _Sample.__table__.c.id
    assert col.primary_key
    generated = col.default.arg(None)  # type: ignore[union-attr]
    assert isinstance(generated, uuid.UUID)


def test_has_timestamp_and_metadata_columns() -> None:
    cols = set(_Sample.__table__.c.keys())
    assert {"id", "created_at", "updated_at", "metadata_", "name"} <= cols
