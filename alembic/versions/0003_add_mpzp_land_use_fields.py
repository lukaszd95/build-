"""add mpzp land use autosave fields

Revision ID: 0003_add_mpzp_land_use_fields
Revises: 0002_add_mpzp_plot_identification_fields
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_add_mpzp_land_use_fields"
down_revision = "0002_add_mpzp_plot_identification_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mpzp_conditions", sa.Column("land_use_primary", sa.Text(), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("land_use_allowed", sa.Text(), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("land_use_forbidden", sa.Text(), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("services_allowed", sa.Boolean(), nullable=True))
    op.add_column("mpzp_conditions", sa.Column("nuisance_services_forbidden", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("mpzp_conditions", "nuisance_services_forbidden")
    op.drop_column("mpzp_conditions", "services_allowed")
    op.drop_column("mpzp_conditions", "land_use_forbidden")
    op.drop_column("mpzp_conditions", "land_use_allowed")
    op.drop_column("mpzp_conditions", "land_use_primary")
