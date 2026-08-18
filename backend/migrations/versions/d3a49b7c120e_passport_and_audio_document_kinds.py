"""Add passport and sound-mark document kinds.

Revision ID: d3a49b7c120e
Revises: 9c7d3e5a1f24
"""

from alembic import op

revision = "d3a49b7c120e"
down_revision = "9c7d3e5a1f24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE documentkind ADD VALUE IF NOT EXISTS 'passport'")
        op.execute("ALTER TYPE documentkind ADD VALUE IF NOT EXISTS 'mark_audio'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely while rows may use them.
    pass
