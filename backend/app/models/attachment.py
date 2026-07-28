import uuid

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Attachment(Base, UUIDMixin, TimestampMixin):
    """A file uploaded to a report section (WP3 S9) — attachment or inline image.

    ``content_type`` is server-sniffed from magic bytes, never the client claim;
    ``storage_key`` locates the blob behind the StorageBackend Protocol;
    ``classification`` is copied from the exercise at upload time so it travels
    with the stored file (WP6 export, WP8-C backup).
    """

    __tablename__ = "attachment"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report.id", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_section.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    classification: Mapped[str | None] = mapped_column(String(50), nullable=True)
