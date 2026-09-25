"""add account deletion requests

Revision ID: 0007_account_deletion_requests
Revises: 0006_uas_fusion_core
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_account_deletion_requests"
down_revision = "0006_uas_fusion_core"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "account_deletion_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pi_username", sa.String(length=128), nullable=False),
        sa.Column("contact_email", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("request_token", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_account_deletion_requests_pi_username", "account_deletion_requests", ["pi_username"])
    op.create_index("ix_account_deletion_requests_contact_email", "account_deletion_requests", ["contact_email"])
    op.create_index("ix_account_deletion_requests_status", "account_deletion_requests", ["status"])
    op.create_index("ix_account_deletion_requests_request_token", "account_deletion_requests", ["request_token"], unique=True)
    op.create_index("ix_account_deletion_requests_created_at", "account_deletion_requests", ["created_at"])

def downgrade():
    op.drop_table("account_deletion_requests")
