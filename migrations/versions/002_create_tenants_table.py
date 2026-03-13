"""Create tenants table

Revision ID: 002
Revises: 001
Create Date: 2026-03-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_name", sa.String(255), nullable=False, unique=True),
        sa.Column("github_url", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_tenants_tenant_name", "tenants", ["tenant_name"])


def downgrade() -> None:
    op.drop_index("ix_tenants_tenant_name", table_name="tenants")
    op.drop_table("tenants")
