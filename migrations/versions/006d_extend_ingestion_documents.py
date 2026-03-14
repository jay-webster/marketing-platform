"""Extend ingestion_documents: add GitHub PR workflow columns

Revision ID: 006d
Revises: 006c
Create Date: 2026-03-14
"""
import sqlalchemy as sa
from alembic import op

revision = "006d"
down_revision = "006c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingestion_documents", sa.Column("destination_folder", sa.Text(), nullable=True))
    op.add_column("ingestion_documents", sa.Column("github_branch", sa.Text(), nullable=True))
    op.add_column("ingestion_documents", sa.Column("github_pr_number", sa.Integer(), nullable=True))
    op.add_column("ingestion_documents", sa.Column("github_pr_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("ingestion_documents", "github_pr_url")
    op.drop_column("ingestion_documents", "github_pr_number")
    op.drop_column("ingestion_documents", "github_branch")
    op.drop_column("ingestion_documents", "destination_folder")
