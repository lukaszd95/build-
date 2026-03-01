"""add parcel area and land use register items for mpzp

Revision ID: 0004_add_mpzp_land_register
Revises: 0003_add_mpzp_land_use_fields
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_mpzp_land_register"
down_revision = "0003_add_mpzp_land_use_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mpzp_conditions", sa.Column("parcel_area_total", sa.Numeric(12, 2), nullable=True))

    op.create_table(
        "mpzp_land_use_register_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.Column("category_symbol", sa.String(length=64), nullable=False),
        sa.Column("area", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["mpzp_conditions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("area >= 0", name="ck_mpzp_land_use_register_item_area_non_negative"),
    )
    op.create_index("ix_mpzp_land_use_register_items_parent_id", "mpzp_land_use_register_items", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_mpzp_land_use_register_items_parent_id", table_name="mpzp_land_use_register_items")
    op.drop_table("mpzp_land_use_register_items")
    op.drop_column("mpzp_conditions", "parcel_area_total")
