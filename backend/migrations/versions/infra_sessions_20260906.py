"""Session revocation."""
from alembic import op
import sqlalchemy as sa

revision = "infra_sessions_20260906"
down_revision = "f2a6c4e18b70"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("resource_budgets", sa.Column("key", sa.String(80), primary_key=True),
                    sa.Column("spent", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_table("resource_budgets")
    op.drop_column("users", "session_version")
