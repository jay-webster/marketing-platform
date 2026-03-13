import enum
import uuid

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class InvitationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invited_email: Mapped[str] = mapped_column(String(255), nullable=False)
    assigned_role: Mapped[str] = mapped_column(String(50), nullable=False)
    issued_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    issued_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    expires_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=InvitationStatus.PENDING
    )

    __table_args__ = (
        CheckConstraint(
            "assigned_role IN ('marketing_manager', 'marketer')",
            name="ck_invitations_assigned_role",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'expired')",
            name="ck_invitations_status",
        ),
        Index("idx_invitations_email_status", "invited_email", "status"),
        Index("idx_invitations_token_hash", "token_hash"),
    )
