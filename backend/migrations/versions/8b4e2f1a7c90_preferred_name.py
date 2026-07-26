"""Имя для обращения в профиле.

ФИО хранится как «Фамилия Имя Отчество», поэтому приветствие по
первому слову получалось по фамилии. Отдельное поле позволяет
задать, как обращаться к человеку.

Revision ID: 8b4e2f1a7c90
Revises: 6f2a1c4d8b30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "8b4e2f1a7c90"
down_revision = "6f2a1c4d8b30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("preferred_name", sa.String(length=120), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "preferred_name")
