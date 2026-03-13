"""Create IAM tables: users, sessions, invitations, audit_log

Revision ID: 001
Revises:
Create Date: 2026-03-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint(
            "role IN ('admin', 'marketing_manager', 'marketer')", name="ck_users_role"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'deactivated')", name="ck_users_status"
        ),
    )
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("idx_users_role_status", "users", ["role", "status"])

    # 2. sessions
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_sessions_user_id", "sessions", ["user_id"])
    op.create_index("idx_sessions_token_hash", "sessions", ["refresh_token_hash"])

    # 3. invitations
    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("invited_email", sa.String(255), nullable=False),
        sa.Column("assigned_role", sa.String(50), nullable=False),
        sa.Column("issued_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.ForeignKeyConstraint(["issued_by"], ["users.id"]),
        sa.CheckConstraint(
            "assigned_role IN ('marketing_manager', 'marketer')",
            name="ck_invitations_assigned_role",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'expired')",
            name="ck_invitations_status",
        ),
    )
    op.create_index("idx_invitations_email_status", "invitations",
                    ["invited_email", "status"])
    op.create_index("idx_invitations_token_hash", "invitations", ["token_hash"])

    # 4. audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_audit_log_actor", "audit_log", ["actor_id"])
    op.create_index("idx_audit_log_timestamp", "audit_log", ["timestamp"],
                    postgresql_ops={"timestamp": "DESC"})


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("invitations")
    op.drop_table("sessions")
    op.drop_table("users")
