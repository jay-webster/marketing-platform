import enum
import uuid

from sqlalchemy import CheckConstraint, DateTime, Enum, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class Role(str, enum.Enum):
    ADMIN = "admin"
    MARKETING_MANAGER = "marketing_manager"
    MARKETER = "marketer"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    DEACTIVATED = "deactivated"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=UserStatus.ACTIVE,
    )
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    deactivated_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('admin', 'marketing_manager', 'marketer')", name="ck_users_role"
        ),
        CheckConstraint(
            "status IN ('active', 'deactivated')", name="ck_users_status"
        ),
        Index("idx_users_email", "email"),
        Index("idx_users_role_status", "role", "status"),
    )
