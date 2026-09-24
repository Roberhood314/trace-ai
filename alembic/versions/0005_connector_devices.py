"""Add persistent connector device registry.

Revision ID: 0005_connector_devices
Revises: 0004_wanted_performance
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_connector_devices"
down_revision = "0004_wanted_performance"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "connector_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("integration_id", sa.String(length=32), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("capabilities_json", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_connector_devices_device_id", "connector_devices", ["device_id"], unique=True)
    op.create_index("ix_connector_devices_integration_id", "connector_devices", ["integration_id"])
    op.create_index("ix_connector_devices_token_hash", "connector_devices", ["token_hash"], unique=True)
    op.create_index("ix_connector_devices_is_active", "connector_devices", ["is_active"])
    op.create_index("ix_connector_devices_created_at", "connector_devices", ["created_at"])
    op.create_index("ix_connector_devices_last_seen_at", "connector_devices", ["last_seen_at"])

def downgrade():
    op.drop_index("ix_connector_devices_last_seen_at", table_name="connector_devices")
    op.drop_index("ix_connector_devices_created_at", table_name="connector_devices")
    op.drop_index("ix_connector_devices_is_active", table_name="connector_devices")
    op.drop_index("ix_connector_devices_token_hash", table_name="connector_devices")
    op.drop_index("ix_connector_devices_integration_id", table_name="connector_devices")
    op.drop_index("ix_connector_devices_device_id", table_name="connector_devices")
    op.drop_table("connector_devices")
