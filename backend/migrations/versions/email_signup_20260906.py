"""One-time email signup requests; accounts exist only after confirmation."""
from alembic import op
import sqlalchemy as sa

revision = "email_signup_20260906"
down_revision = "infra_sessions_20260906"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("pending_signups",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_pending_signups_email", "pending_signups", ["email"])
    op.create_index("ix_pending_signups_expires_at", "pending_signups", ["expires_at"])

def downgrade():
    op.drop_table("pending_signups")
