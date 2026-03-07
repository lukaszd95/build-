"""add users.is_admin flag

Revision ID: 0008_add_user_is_admin
Revises: 0007_add_mpzp_parking_environment_fields
Create Date: 2026-03-07
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_add_user_is_admin"
down_revision = "0007_add_mpzp_parking_environment_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    if bind.dialect.name != "sqlite":
        op.alter_column("users", "is_admin", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "is_admin")
