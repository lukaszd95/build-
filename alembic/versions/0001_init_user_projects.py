"""init user scoped project schema

Revision ID: 0001_init_user_projects
Revises:
Create Date: 2026-02-20
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_init_user_projects"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "projects_v2",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_projects_v2_user_id", "projects_v2", ["user_id"], unique=False)

    op.create_table(
        "mpzp_conditions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects_v2.id", ondelete="CASCADE"), nullable=False),
        sa.Column("max_height", sa.Numeric(10, 2), nullable=True),
        sa.Column("max_area", sa.Numeric(10, 2), nullable=True),
        sa.Column("building_line", sa.String(length=255), nullable=True),
        sa.Column("roof_angle", sa.Numeric(10, 2), nullable=True),
        sa.Column("biologically_active_area", sa.Numeric(10, 2), nullable=True),
        sa.Column("allowed_functions", sa.Text(), nullable=True),
        sa.Column("parking_min", sa.Integer(), nullable=True),
        sa.Column("intensity_min", sa.Numeric(10, 2), nullable=True),
        sa.Column("intensity_max", sa.Numeric(10, 2), nullable=True),
        sa.Column("frontage_min", sa.Numeric(10, 2), nullable=True),
        sa.Column("floors_max", sa.Integer(), nullable=True),
        sa.Column("basement_allowed", sa.Boolean(), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("project_id"),
    )

    op.create_table(
        "cost_estimates_v2",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects_v2.id", ondelete="CASCADE"), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="PLN"),
        sa.Column("net_total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("gross_total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("contingency_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("project_id"),
    )

    op.create_table(
        "cost_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("estimate_id", sa.Integer(), sa.ForeignKey("cost_estimates_v2.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_cost_item_quantity_non_negative"),
        sa.CheckConstraint("unit_price >= 0", name="ck_cost_item_unit_price_non_negative"),
    )

    op.create_table(
        "design_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects_v2.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dimension", sa.String(length=2), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("project_id", "dimension", "version", name="uq_asset_project_dim_version"),
    )


def downgrade() -> None:
    op.drop_table("design_assets")
    op.drop_table("cost_items")
    op.drop_table("cost_estimates_v2")
    op.drop_table("mpzp_conditions")
    op.drop_index("ix_projects_v2_user_id", table_name="projects_v2")
    op.drop_table("projects_v2")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
