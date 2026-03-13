"""ChatMessage model — individual turns within a ChatSession."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    # "user" or "assistant"
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # True when the assistant response contains AI-generated marketing material
    is_generated_content: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # [{id, title, source_file}] for assistant messages; null for user messages
    source_documents: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    session: Mapped["ChatSession"] = relationship(  # noqa: F821
        "ChatSession", back_populates="messages"
    )

    __table_args__ = (
        Index("idx_chat_messages_session_id", "session_id", "created_at"),
    )
