"""Create GitHub Bridge tables: github_connections, repo_structure_configs, scaffolding_runs

Revision ID: 003
Revises: 002
Create Date: 2026-03-13
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "github_connections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("repository_url", sa.Text, nullable=False),
        sa.Column("encrypted_token", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("connected_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_scaffolded_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial unique index: only one row may have status = 'active'
    op.execute(
        "CREATE UNIQUE INDEX ix_github_connections_one_active "
        "ON github_connections (status) WHERE status = 'active'"
    )
    op.create_index("ix_github_connections_connected_by", "github_connections", ["connected_by"])

    op.create_table(
        "repo_structure_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("folders", JSONB, nullable=False),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_repo_structure_configs_is_default", "repo_structure_configs", ["is_default"])

    op.create_table(
        "scaffolding_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("connection_id", UUID(as_uuid=True), sa.ForeignKey("github_connections.id"), nullable=False),
        sa.Column("triggered_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("folders_created", sa.Integer, nullable=False, server_default="0"),
        sa.Column("folders_skipped", sa.Integer, nullable=False, server_default="0"),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("error_detail", sa.Text, nullable=True),
    )
    op.execute(
        "CREATE INDEX ix_scaffolding_runs_connection_id "
        "ON scaffolding_runs (connection_id, ran_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_scaffolding_runs_connection_id")
    op.drop_table("scaffolding_runs")
    op.drop_index("ix_repo_structure_configs_is_default", table_name="repo_structure_configs")
    op.drop_table("repo_structure_configs")
    op.execute("DROP INDEX IF EXISTS ix_github_connections_one_active")
    op.drop_index("ix_github_connections_connected_by", table_name="github_connections")
    op.drop_table("github_connections")
