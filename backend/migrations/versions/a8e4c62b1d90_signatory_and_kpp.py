"""Подписант заявления и КПП заявителя.

Revision ID: a8e4c62b1d90
Revises: f7c2a91d4e60
"""

import sqlalchemy as sa
from alembic import op

revision = "a8e4c62b1d90"
down_revision = "f7c2a91d4e60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("clients") as batch_op:
        batch_op.add_column(sa.Column("kpp", sa.String(length=20), nullable=True))

    with op.batch_alter_table("trademark_application_drafts") as batch_op:
        batch_op.add_column(
            sa.Column(
                "filing_method",
                sa.String(length=20),
                nullable=False,
                server_default="electronic",
            )
        )
        batch_op.add_column(sa.Column("signatory_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("signatory_position", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("signature_date", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("trademark_application_drafts") as batch_op:
        batch_op.drop_column("signature_date")
        batch_op.drop_column("signatory_position")
        batch_op.drop_column("signatory_name")
        batch_op.drop_column("filing_method")

    with op.batch_alter_table("clients") as batch_op:
        batch_op.drop_column("kpp")
