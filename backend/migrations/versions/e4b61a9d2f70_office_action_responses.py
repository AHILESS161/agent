"""Add office action response drafts.

Revision ID: e4b61a9d2f70
Revises: d3a49b7c120e
"""

import sqlalchemy as sa
from alembic import op

revision = "e4b61a9d2f70"
down_revision = "d3a49b7c120e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "office_action_responses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("notice_document_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("response_deadline", sa.String(length=32), nullable=True),
        sa.Column("homogeneity_facts_json", sa.JSON(), nullable=False),
        sa.Column("distinctiveness_evidence_json", sa.JSON(), nullable=False),
        sa.Column("additional_facts", sa.Text(), nullable=True),
        sa.Column("notice_summary", sa.Text(), nullable=True),
        sa.Column("response_summary", sa.Text(), nullable=True),
        sa.Column("missing_evidence_json", sa.JSON(), nullable=False),
        sa.Column("draft_text", sa.Text(), nullable=True),
        sa.Column("llm_model", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["trademark_application_drafts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["notice_document_id"], ["source_documents.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_office_action_responses_application_id", "office_action_responses", ["application_id"])
    op.create_index("ix_office_action_responses_id", "office_action_responses", ["id"])


def downgrade() -> None:
    op.drop_index("ix_office_action_responses_id", table_name="office_action_responses")
    op.drop_index("ix_office_action_responses_application_id", table_name="office_action_responses")
    op.drop_table("office_action_responses")
