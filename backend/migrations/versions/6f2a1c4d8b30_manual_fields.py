"""Ручной ввод значения поля без документа-источника.

Значение, внесённое специалистом, документа не имеет: в выписке его
могло не быть вовсе (адрес места жительства ИП в ЕГРИП скрыт) либо
поле заведено сверх маппинга. Поэтому ``document_id`` становится
необязательным.

Revision ID: 6f2a1c4d8b30
Revises: 574d31bbc19d
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "6f2a1c4d8b30"
down_revision = "574d31bbc19d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("extracted_fields") as batch:
        batch.alter_column(
            "document_id", existing_type=sa.Integer(), nullable=True
        )


def downgrade() -> None:
    # Записи без документа — ручной ввод; вернуть NOT NULL можно
    # только удалив их, поэтому откат их отбрасывает.
    op.execute("DELETE FROM extracted_fields WHERE document_id IS NULL")
    with op.batch_alter_table("extracted_fields") as batch:
        batch.alter_column(
            "document_id", existing_type=sa.Integer(), nullable=False
        )
