"""add mpzp plot identification fields

Revision ID: 0002_add_mpzp_plot_identification_fields
Revises: 0001_init_user_projects
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_mpzp_plot_identification_fields"
down_revision = "0001_init_user_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("mpzp_conditions")}

    if "plot_number" not in existing_columns:
        op.add_column("mpzp_conditions", sa.Column("plot_number", sa.String(length=120), nullable=True))
    if "cadastral_district" not in existing_columns:
        op.add_column("mpzp_conditions", sa.Column("cadastral_district", sa.String(length=255), nullable=True))
    if "street" not in existing_columns:
        op.add_column("mpzp_conditions", sa.Column("street", sa.String(length=255), nullable=True))
    if "city" not in existing_columns:
        op.add_column("mpzp_conditions", sa.Column("city", sa.String(length=255), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("mpzp_conditions")}

    if "city" in existing_columns:
        op.drop_column("mpzp_conditions", "city")
    if "street" in existing_columns:
        op.drop_column("mpzp_conditions", "street")
    if "cadastral_district" in existing_columns:
        op.drop_column("mpzp_conditions", "cadastral_district")
    if "plot_number" in existing_columns:
        op.drop_column("mpzp_conditions", "plot_number")
