"""Extend knowledge_base_documents: nullable processed_document_id, add synced_document_id FK

Revision ID: 006c
Revises: 006b
Create Date: 2026-03-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "006c"
down_revision = "006b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make processed_document_id nullable (existing rows retain their values)
    op.alter_column("knowledge_base_documents", "processed_document_id", nullable=True)

    # Add synced_document_id FK
    op.add_column(
        "knowledge_base_documents",
        sa.Column(
            "synced_document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("synced_documents.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )

    # Unique index: at most one KB doc per synced document
    op.create_index(
        "idx_kb_documents_synced_document",
        "knowledge_base_documents",
        ["synced_document_id"],
        unique=True,
        postgresql_where=sa.text("synced_document_id IS NOT NULL"),
    )

    # XOR check: exactly one source must be set
    op.create_check_constraint(
        "ck_kb_doc_source_xor",
        "knowledge_base_documents",
        "(processed_document_id IS NOT NULL) != (synced_document_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_kb_doc_source_xor", "knowledge_base_documents", type_="check")
    op.drop_index("idx_kb_documents_synced_document", table_name="knowledge_base_documents")
    op.drop_column("knowledge_base_documents", "synced_document_id")
    op.alter_column("knowledge_base_documents", "processed_document_id", nullable=False)
