"""Add brand_images and generation_requests tables

Revision ID: 008
Revises: 007
Create Date: 2026-03-15
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "brand_images",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("gcs_object_name", sa.String(500), nullable=False, unique=True),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("display_title", sa.String(255), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "idx_brand_images_active",
        "brand_images",
        ["is_active"],
        postgresql_where=sa.text("is_active = TRUE"),
    )
    op.create_index("idx_brand_images_source", "brand_images", ["source"])

    op.create_table(
        "generation_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("output_type", sa.String(50), nullable=False),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("pdf_template", sa.String(100), nullable=True),
        sa.Column("selected_image_ids", JSON, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("result_text", sa.Text, nullable=True),
        sa.Column("result_pdf_gcs_name", sa.String(500), nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_generation_requests_user_id", "generation_requests", ["user_id"])
    op.create_index(
        "idx_generation_requests_user_created",
        "generation_requests",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_generation_requests_user_created", table_name="generation_requests")
    op.drop_index("idx_generation_requests_user_id", table_name="generation_requests")
    op.drop_table("generation_requests")

    op.drop_index("idx_brand_images_source", table_name="brand_images")
    op.drop_index("idx_brand_images_active", table_name="brand_images")
    op.drop_table("brand_images")
