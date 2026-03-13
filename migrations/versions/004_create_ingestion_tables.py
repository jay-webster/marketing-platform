"""Create Ingestion Pipeline tables: ingestion_batches, ingestion_documents, processed_documents

Revision ID: 004
Revises: 003
Create Date: 2026-03-13
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_batches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("submitted_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("source_folder_name", sa.Text, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="in_progress"),
        sa.Column("total_documents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_ingestion_batches_submitted_by", "ingestion_batches", ["submitted_by"])
    op.create_index("ix_ingestion_batches_submitted_at", "ingestion_batches", ["submitted_at"])

    op.create_table(
        "ingestion_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("batch_id", UUID(as_uuid=True), sa.ForeignKey("ingestion_batches.id"), nullable=False),
        sa.Column("original_filename", sa.Text, nullable=False),
        sa.Column("original_file_type", sa.String(10), nullable=False),
        sa.Column("relative_path", sa.Text, nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False),
        sa.Column("gcs_object_path", sa.Text, nullable=False),
        sa.Column("processing_status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reprocessing_note", sa.Text, nullable=True),
    )
    op.create_index("ix_ingestion_documents_batch_id", "ingestion_documents", ["batch_id"])
    # Partial index for queue worker: only index rows in queued state
    op.execute(
        "CREATE INDEX ix_ingestion_documents_queued "
        "ON ingestion_documents (queued_at) WHERE processing_status = 'queued'"
    )

    op.create_table(
        "processed_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("ingestion_document_id", UUID(as_uuid=True), sa.ForeignKey("ingestion_documents.id"), nullable=False, unique=True),
        sa.Column("markdown_content", sa.Text, nullable=False),
        sa.Column("extracted_title", sa.Text, nullable=True),
        sa.Column("extracted_author", sa.Text, nullable=True),
        sa.Column("extracted_date", sa.Text, nullable=True),
        sa.Column("review_status", sa.String(30), nullable=False, server_default="pending_review"),
        sa.Column("reviewed_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_processed_documents_review_status", "processed_documents", ["review_status"])


def downgrade() -> None:
    op.drop_index("ix_processed_documents_review_status", table_name="processed_documents")
    op.drop_table("processed_documents")
    op.execute("DROP INDEX IF EXISTS ix_ingestion_documents_queued")
    op.drop_index("ix_ingestion_documents_batch_id", table_name="ingestion_documents")
    op.drop_table("ingestion_documents")
    op.drop_index("ix_ingestion_batches_submitted_at", table_name="ingestion_batches")
    op.drop_index("ix_ingestion_batches_submitted_by", table_name="ingestion_batches")
    op.drop_table("ingestion_batches")
