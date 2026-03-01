"""add mpzp building parameters fields

Revision ID: 0005_add_mpzp_building_parameters_fields
Revises: 0004_add_mpzp_land_register
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_add_mpzp_building_parameters_fields"
down_revision = "0004_add_mpzp_land_register"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mpzp_conditions", sa.Column("max_building_height", sa.Numeric(10, 2), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("max_storeys_above", sa.Integer(), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("max_storeys_below", sa.Integer(), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("max_ridge_height", sa.Numeric(10, 2), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("max_eaves_height", sa.Numeric(10, 2), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("min_building_intensity", sa.Numeric(10, 2), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("max_building_intensity", sa.Numeric(10, 2), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("max_building_coverage", sa.Numeric(10, 2), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("min_biologically_active_share", sa.Numeric(5, 2), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("min_front_elevation_width", sa.Numeric(10, 2), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("max_front_elevation_width", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("mpzp_conditions", "max_front_elevation_width")
    op.drop_column("mpzp_conditions", "min_front_elevation_width")
    op.drop_column("mpzp_conditions", "min_biologically_active_share")
    op.drop_column("mpzp_conditions", "max_building_coverage")
    op.drop_column("mpzp_conditions", "max_building_intensity")
    op.drop_column("mpzp_conditions", "min_building_intensity")
    op.drop_column("mpzp_conditions", "max_eaves_height")
    op.drop_column("mpzp_conditions", "max_ridge_height")
    op.drop_column("mpzp_conditions", "max_storeys_below")
    op.drop_column("mpzp_conditions", "max_storeys_above")
    op.drop_column("mpzp_conditions", "max_building_height")
