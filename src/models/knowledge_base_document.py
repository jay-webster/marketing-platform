"""KnowledgeBaseDocument model — indexing state for approved ProcessedDocuments."""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class KBIndexStatus(str, enum.Enum):
    QUEUED = "queued"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"
    REMOVED = "removed"


class KnowledgeBaseDocument(Base):
    __tablename__ = "knowledge_base_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    processed_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processed_documents.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )
    synced_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("synced_documents.id", ondelete="CASCADE"),
        nullable=True,
    )
    index_status: Mapped[str] = mapped_column(
        Text, nullable=False, default=KBIndexStatus.QUEUED.value
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    removed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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

    chunks: Mapped[list["ContentChunk"]] = relationship(  # noqa: F821
        "ContentChunk", back_populates="kb_document", cascade="all, delete-orphan"
    )
    synced_document: Mapped["SyncedDocument | None"] = relationship(  # noqa: F821
        "SyncedDocument", back_populates="kb_document"
    )

    __table_args__ = (
        # Partial index for queue worker — only rows needing processing
        Index(
            "idx_kb_documents_status",
            "index_status",
            postgresql_where="index_status = 'queued'",
        ),
        Index(
            "idx_kb_documents_indexed",
            "indexed_at",
            postgresql_where="index_status = 'indexed'",
        ),
        Index(
            "idx_kb_documents_synced_document",
            "synced_document_id",
            unique=True,
            postgresql_where="synced_document_id IS NOT NULL",
        ),
    )
