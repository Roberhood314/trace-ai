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

def _index_names(inspector):
    if "connector_devices" not in inspector.get_table_names():
        return set()
    return {x["name"] for x in inspector.get_indexes("connector_devices") if x.get("name")}

def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "connector_devices" not in inspector.get_table_names():
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
        inspector = sa.inspect(bind)
    existing = _index_names(inspector)
    desired = {
        "ix_connector_devices_device_id": (["device_id"], True),
        "ix_connector_devices_integration_id": (["integration_id"], False),
        "ix_connector_devices_token_hash": (["token_hash"], True),
        "ix_connector_devices_is_active": (["is_active"], False),
        "ix_connector_devices_created_at": (["created_at"], False),
        "ix_connector_devices_last_seen_at": (["last_seen_at"], False),
    }
    for name, (cols, unique) in desired.items():
        if name not in existing:
            op.create_index(name, "connector_devices", cols, unique=unique)

def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "connector_devices" not in inspector.get_table_names():
        return
    existing = _index_names(inspector)
    for name in [
        "ix_connector_devices_last_seen_at",
        "ix_connector_devices_created_at",
        "ix_connector_devices_is_active",
        "ix_connector_devices_token_hash",
        "ix_connector_devices_integration_id",
        "ix_connector_devices_device_id",
    ]:
        if name in existing:
            op.drop_index(name, table_name="connector_devices")
    op.drop_table("connector_devices")
