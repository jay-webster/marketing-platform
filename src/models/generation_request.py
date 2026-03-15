"""GenerationRequest model — record of each content generation action."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class GenerationRequest(Base):
    __tablename__ = "generation_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    output_type: Mapped[str] = mapped_column(String(50), nullable=False)  # email | linkedin | pdf
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_template: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # JSON array of UUID strings — snapshot of selected brand_image ids at generation time
    selected_image_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    # Stores JSON-serialised result dict for email/linkedin; None for pdf
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # GCS object name of generated PDF; None for text types
    result_pdf_gcs_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_generation_requests_user_id", "user_id"),
        Index("idx_generation_requests_user_created", "user_id", "created_at"),
    )
