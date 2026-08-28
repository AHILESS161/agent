"""Application-specific representative details.

Revision ID: e8f3c1a72b90
Revises: d9e5b7a21c40
"""

from alembic import op
import sqlalchemy as sa


revision = "e8f3c1a72b90"
down_revision = "d9e5b7a21c40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("client_representatives") as batch_op:
        batch_op.add_column(sa.Column("address", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("is_patent_attorney", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(
            sa.Column("patent_attorney_registration_number", sa.String(length=50), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "authority_type",
                sa.String(length=30),
                server_default="power_of_attorney",
                nullable=False,
            )
        )

    with op.batch_alter_table("trademark_application_drafts") as batch_op:
        batch_op.add_column(sa.Column("representative_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_trademark_application_drafts_representative_id",
            ["representative_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_application_representative",
            "client_representatives",
            ["representative_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("trademark_application_drafts") as batch_op:
        batch_op.drop_constraint("fk_application_representative", type_="foreignkey")
        batch_op.drop_index("ix_trademark_application_drafts_representative_id")
        batch_op.drop_column("representative_id")

    with op.batch_alter_table("client_representatives") as batch_op:
        batch_op.drop_column("authority_type")
        batch_op.drop_column("patent_attorney_registration_number")
        batch_op.drop_column("is_patent_attorney")
        batch_op.drop_column("address")
