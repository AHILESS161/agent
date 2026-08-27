"""Выбор бумажного свидетельства.

Revision ID: c1f7b8a42d61
Revises: a8e4c62b1d90
"""

import sqlalchemy as sa
from alembic import op

revision = "c1f7b8a42d61"
down_revision = "a8e4c62b1d90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("trademark_application_drafts") as batch_op:
        batch_op.add_column(
            sa.Column(
                "request_paper_certificate",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("trademark_application_drafts") as batch_op:
        batch_op.drop_column("request_paper_certificate")
