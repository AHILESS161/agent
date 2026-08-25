"""Один класс МКТУ на одну заявку.

Revision ID: f7c2a91d4e60
Revises: e4b61a9d2f70
"""

from alembic import op

revision = "f7c2a91d4e60"
down_revision = "e4b61a9d2f70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # В dev-режиме React может дважды вызвать загрузочный effect. Старые базы
    # поэтому иногда содержат два одинаковых предложения одного класса.
    op.execute(
        """
        DELETE FROM nice_class_suggestions
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM nice_class_suggestions
            GROUP BY application_id, class_number
        )
        """
    )
    op.create_index(
        "uq_nice_class_suggestions_application_class",
        "nice_class_suggestions",
        ["application_id", "class_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_nice_class_suggestions_application_class",
        table_name="nice_class_suggestions",
    )
