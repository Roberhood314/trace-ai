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

_TABLE = "account_deletion_requests"
_INDEXES = [
    ("ix_account_deletion_requests_pi_username", ["pi_username"], False),
    ("ix_account_deletion_requests_contact_email", ["contact_email"], False),
    ("ix_account_deletion_requests_status", ["status"], False),
    ("ix_account_deletion_requests_request_token", ["request_token"], True),
    ("ix_account_deletion_requests_created_at", ["created_at"], False),
]

def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("pi_username", sa.String(length=128), nullable=False),
            sa.Column("contact_email", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
            sa.Column("request_token", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("processed_at", sa.DateTime(), nullable=True),
        )

    # Re-inspect because the table may have just been created, or may already
    # exist from an older bootstrap path. Add only missing indexes.
    inspector = sa.inspect(bind)
    existing = {idx["name"] for idx in inspector.get_indexes(_TABLE)}
    for name, columns, unique in _INDEXES:
        if name not in existing:
            op.create_index(name, _TABLE, columns, unique=unique)

def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(_TABLE):
        op.drop_table(_TABLE)
