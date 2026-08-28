"""Аренда и дедупликация фоновых заданий.

Revision ID: d9e5b7a21c40
Revises: c1f7b8a42d61
"""

import sqlalchemy as sa
from alembic import op

revision = "d9e5b7a21c40"
down_revision = "c1f7b8a42d61"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("background_jobs") as batch_op:
        batch_op.add_column(sa.Column("deduplication_key", sa.String(255)))
        batch_op.add_column(sa.Column("worker_id", sa.String(255)))
        batch_op.add_column(sa.Column("attempt_token", sa.String(64)))
        batch_op.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("available_at", sa.DateTime(timezone=True)))

    op.create_index(
        "ix_background_jobs_deduplication_key",
        "background_jobs",
        ["deduplication_key"],
        unique=True,
    )
    op.create_index(
        "ix_background_jobs_worker_id",
        "background_jobs",
        ["worker_id"],
    )
    op.create_index(
        "ix_background_jobs_lease_expires_at",
        "background_jobs",
        ["lease_expires_at"],
    )
    op.create_index(
        "ix_background_jobs_available_at",
        "background_jobs",
        ["available_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_background_jobs_available_at", table_name="background_jobs")
    op.drop_index("ix_background_jobs_lease_expires_at", table_name="background_jobs")
    op.drop_index("ix_background_jobs_worker_id", table_name="background_jobs")
    op.drop_index("ix_background_jobs_deduplication_key", table_name="background_jobs")
    with op.batch_alter_table("background_jobs") as batch_op:
        batch_op.drop_column("available_at")
        batch_op.drop_column("lease_expires_at")
        batch_op.drop_column("heartbeat_at")
        batch_op.drop_column("attempt_token")
        batch_op.drop_column("worker_id")
        batch_op.drop_column("deduplication_key")
