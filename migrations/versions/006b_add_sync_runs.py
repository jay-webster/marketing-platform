"""Add sync_runs table for GitHub sync execution history

Revision ID: 006b
Revises: 006a
Create Date: 2026-03-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "006b"
down_revision = "006a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "connection_id",
            UUID(as_uuid=True),
            sa.ForeignKey("github_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "triggered_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("trigger_type", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False, server_default="in_progress"),
        sa.Column("files_indexed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("files_removed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("files_unchanged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_detail", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_sync_runs_connection_started",
        "sync_runs",
        ["connection_id", sa.text("started_at DESC")],
    )
    op.create_index(
        "idx_sync_runs_in_progress",
        "sync_runs",
        ["connection_id", "outcome"],
        postgresql_where=sa.text("outcome = 'in_progress'"),
    )


def downgrade() -> None:
    op.drop_index("idx_sync_runs_in_progress", table_name="sync_runs")
    op.drop_index("idx_sync_runs_connection_started", table_name="sync_runs")
    op.drop_table("sync_runs")
