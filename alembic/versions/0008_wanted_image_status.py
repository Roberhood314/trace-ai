"""add wanted image sync metadata

Revision ID: 0008_wanted_image_status
Revises: 0007_account_deletion_requests
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_wanted_image_status"
down_revision = "0007_account_deletion_requests"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("wanted_records")}
    with op.batch_alter_table("wanted_records") as batch:
        if "image_status" not in columns:
            batch.add_column(sa.Column("image_status", sa.String(length=24), nullable=False, server_default="unchecked"))
        if "image_checked_at" not in columns:
            batch.add_column(sa.Column("image_checked_at", sa.DateTime(), nullable=True))
    inspector = sa.inspect(bind)
    indexes = {i["name"] for i in inspector.get_indexes("wanted_records")}
    if "ix_wanted_records_image_status" not in indexes:
        op.create_index("ix_wanted_records_image_status", "wanted_records", ["image_status"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {i["name"] for i in inspector.get_indexes("wanted_records")}
    if "ix_wanted_records_image_status" in indexes:
        op.drop_index("ix_wanted_records_image_status", table_name="wanted_records")
    columns = {c["name"] for c in inspector.get_columns("wanted_records")}
    with op.batch_alter_table("wanted_records") as batch:
        if "image_checked_at" in columns:
            batch.drop_column("image_checked_at")
        if "image_status" in columns:
            batch.drop_column("image_status")
