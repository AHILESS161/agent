"""Срочность дела и его владелец.

Приоритет — срочность в работе поверенного, а не конвенционный
приоритет заявки (тот живёт в ``priority_claim``).

Владелец нужен, чтобы поверенные вели свои дела и не мешали друг
другу. Существующие дела закрепляются за назначенным юристом, иначе
после обновления они пропали бы из его списка.

Revision ID: 9c7d3e5a1f24
Revises: 8b4e2f1a7c90
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "9c7d3e5a1f24"
down_revision = "8b4e2f1a7c90"
branch_labels = None
depends_on = None

TABLE = "trademark_application_drafts"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "priority",
            sa.Enum("low", "medium", "high", name="casepriority"),
            nullable=False,
            server_default="medium",
        ),
    )
    op.add_column(
        TABLE, sa.Column("created_by_user_id", sa.Integer(), nullable=True)
    )
    op.create_index(
        f"ix_{TABLE}_created_by_user_id", TABLE, ["created_by_user_id"]
    )

    # Дела закрепляются за назначенным юристом; если его нет —
    # за первым пользователем с ролью юриста, чтобы ни одно дело
    # не осталось без владельца и не исчезло из списков.
    op.execute(
        f"""
        UPDATE {TABLE}
           SET created_by_user_id = COALESCE(
                 assigned_lawyer_id,
                 (SELECT id FROM users WHERE role = 'lawyer' ORDER BY id LIMIT 1)
               )
         WHERE created_by_user_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index(f"ix_{TABLE}_created_by_user_id", table_name=TABLE)
    op.drop_column(TABLE, "created_by_user_id")
    op.drop_column(TABLE, "priority")
