"""Extend github_connections: add last_synced_at and default_branch

Revision ID: 006e
Revises: 006d
Create Date: 2026-03-14
"""
import sqlalchemy as sa
from alembic import op

revision = "006e"
down_revision = "006d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("github_connections", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("github_connections", sa.Column("default_branch", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("github_connections", "default_branch")
    op.drop_column("github_connections", "last_synced_at")
