"""add mpzp parking and environmental autosave fields

Revision ID: 0007_add_mpzp_parking_environment_fields
Revises: 0006_add_mpzp_roof_architecture_fields
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_add_mpzp_parking_environment_fields"
down_revision = "0006_add_mpzp_roof_architecture_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mpzp_conditions", sa.Column("parking_required_info", sa.Text(), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("parking_spaces_per_unit", sa.Numeric(10, 2), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("parking_spaces_per_100sqm_services", sa.Numeric(10, 2), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("parking_disability_requirement", sa.Text(), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("conservation_protection_zone", sa.Text(), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("nature_protection_zone", sa.Text(), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("noise_emission_limits", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("mpzp_conditions", "noise_emission_limits")
    op.drop_column("mpzp_conditions", "nature_protection_zone")
    op.drop_column("mpzp_conditions", "conservation_protection_zone")
    op.drop_column("mpzp_conditions", "parking_disability_requirement")
    op.drop_column("mpzp_conditions", "parking_spaces_per_100sqm_services")
    op.drop_column("mpzp_conditions", "parking_spaces_per_unit")
    op.drop_column("mpzp_conditions", "parking_required_info")
