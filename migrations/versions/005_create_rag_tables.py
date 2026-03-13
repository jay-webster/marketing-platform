"""Create RAG tables: chat_sessions, chat_messages, knowledge_base_documents, content_chunks

Revision ID: 005
Revises: 004
Create Date: 2026-03-13
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "chat_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_chat_sessions_user_id", "chat_sessions", ["user_id"])
    op.create_index(
        "idx_chat_sessions_user_active",
        "chat_sessions",
        ["user_id", "last_active_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_generated_content", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source_documents", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_chat_messages_session_id", "chat_messages", ["session_id", "created_at"])

    op.create_table(
        "knowledge_base_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "processed_document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("processed_documents.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("index_status", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_kb_documents_status",
        "knowledge_base_documents",
        ["index_status"],
        postgresql_where=sa.text("index_status = 'queued'"),
    )
    op.create_index(
        "idx_kb_documents_indexed",
        "knowledge_base_documents",
        ["indexed_at"],
        postgresql_where=sa.text("index_status = 'indexed'"),
    )

    # content_chunks uses pgvector — column type created via raw SQL
    op.execute(
        """
        CREATE TABLE content_chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            knowledge_base_document_id UUID NOT NULL
                REFERENCES knowledge_base_documents(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content_text TEXT NOT NULL,
            embedding vector(512) NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_content_chunks_kb_doc_id ON content_chunks (knowledge_base_document_id)"
    )
    op.execute(
        "CREATE INDEX idx_content_chunks_embedding ON content_chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m=24, ef_construction=64)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS content_chunks")
    op.drop_table("knowledge_base_documents")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.execute("DROP EXTENSION IF EXISTS vector")
