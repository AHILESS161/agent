"""Reusable applicant profile for client accounts.

Revision ID: f2a6c4e18b70
Revises: e8f3c1a72b90
"""

from alembic import op
import sqlalchemy as sa


revision = "f2a6c4e18b70"
down_revision = "e8f3c1a72b90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("applicant_profile_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("applicant_profile_json")
