"""ContentChunk model — vector store for indexed document segments."""
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class ContentChunk(Base):
    __tablename__ = "content_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    knowledge_base_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("knowledge_base_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 0-based position within the source document
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # Frontmatter-prepended section text — what was embedded
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Voyage AI voyage-3-lite: 512 dimensions
    embedding: Mapped[list] = mapped_column(Vector(512), nullable=False)
    # Parsed frontmatter dict for metadata filtering
    # Attribute renamed to avoid conflict with SQLAlchemy's reserved `metadata` class attr
    doc_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    kb_document: Mapped["KnowledgeBaseDocument"] = relationship(  # noqa: F821
        "KnowledgeBaseDocument", back_populates="chunks"
    )

    # HNSW index and kb_doc_id index are created via raw SQL in the migration.
    # SQLAlchemy ORM does not support pgvector index expressions natively.
