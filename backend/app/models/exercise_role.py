import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class ExerciseRole(Base, UUIDMixin):
    __tablename__ = "exercise_role"
    __table_args__ = (UniqueConstraint("exercise_id", "user_id", "role_key", name="uq_exercise_role"),)

    # exercise_id: no DB FK yet — the `exercise` table lands in Phase D (migration
    # 0004), which adds the FK constraint. Indexed UUID scope key (the route path param).
    exercise_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    role_key: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
