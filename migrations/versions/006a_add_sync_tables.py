"""Add synced_documents table for GitHub repo sync

Revision ID: 006a
Revises: 005
Create Date: 2026-03-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "006a"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "synced_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "connection_id",
            UUID(as_uuid=True),
            sa.ForeignKey("github_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("repo_path", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("content_sha", sa.Text(), nullable=False),
        sa.Column("folder", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("connection_id", "repo_path", name="uq_synced_documents_connection_path"),
    )
    op.create_index("idx_synced_docs_connection_active", "synced_documents", ["connection_id", "is_active"])
    op.create_index("idx_synced_docs_content_sha", "synced_documents", ["content_sha"])


def downgrade() -> None:
    op.drop_index("idx_synced_docs_content_sha", table_name="synced_documents")
    op.drop_index("idx_synced_docs_connection_active", table_name="synced_documents")
    op.drop_table("synced_documents")
