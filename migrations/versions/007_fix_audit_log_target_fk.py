"""Drop FK constraint on audit_log.target_id — target can be any entity, not just users

Revision ID: 007
Revises: 006e
Create Date: 2026-03-14
"""
from alembic import op

revision = "007"
down_revision = "006e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("audit_log_target_id_fkey", "audit_log", type_="foreignkey")


def downgrade() -> None:
    op.create_foreign_key(
        "audit_log_target_id_fkey",
        "audit_log",
        "users",
        ["target_id"],
        ["id"],
        ondelete="SET NULL",
    )
