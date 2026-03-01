"""add mpzp roof architecture fields

Revision ID: 0006_add_mpzp_roof_architecture_fields
Revises: 0005_add_mpzp_building_parameters_fields
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_add_mpzp_roof_architecture_fields"
down_revision = "0005_add_mpzp_building_parameters_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mpzp_conditions", sa.Column("roof_type_allowed", sa.Text(), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("roof_slope_min_deg", sa.Numeric(5, 2), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("roof_slope_max_deg", sa.Numeric(5, 2), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("ridge_direction_required", sa.Text(), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("roof_cover_material_limits", sa.Text(), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("facade_roof_color_limits", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("mpzp_conditions", "facade_roof_color_limits")
    op.drop_column("mpzp_conditions", "roof_cover_material_limits")
    op.drop_column("mpzp_conditions", "ridge_direction_required")
    op.drop_column("mpzp_conditions", "roof_slope_max_deg")
    op.drop_column("mpzp_conditions", "roof_slope_min_deg")
    op.drop_column("mpzp_conditions", "roof_type_allowed")
