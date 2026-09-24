"""Add persistent UAS fusion core.

Revision ID: 0006_uas_fusion_core
Revises: 0005_connector_devices
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_uas_fusion_core"
down_revision = "0005_connector_devices"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "uas_observations" not in tables:
        op.create_table(
            "uas_observations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("observation_key", sa.String(255), nullable=False),
            sa.Column("source", sa.String(32), nullable=False),
            sa.Column("source_track_id", sa.String(128), nullable=True),
            sa.Column("observed_at", sa.DateTime(), nullable=False),
            sa.Column("received_at", sa.DateTime(), nullable=False),
            sa.Column("latitude", sa.Float(), nullable=True),
            sa.Column("longitude", sa.Float(), nullable=True),
            sa.Column("altitude_m", sa.Float(), nullable=True),
            sa.Column("speed_mps", sa.Float(), nullable=True),
            sa.Column("heading_deg", sa.Float(), nullable=True),
            sa.Column("observer_latitude", sa.Float(), nullable=True),
            sa.Column("observer_longitude", sa.Float(), nullable=True),
            sa.Column("observer_heading_deg", sa.Float(), nullable=True),
            sa.Column("classification", sa.String(32), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(128), nullable=True),
        )
        op.create_index("ix_uas_obs_key", "uas_observations", ["observation_key"], unique=True)
        op.create_index("ix_uas_obs_source_time", "uas_observations", ["source", "observed_at"])
        op.create_index("ix_uas_obs_source_track", "uas_observations", ["source_track_id"])

    if "uas_tracks_core" not in tables:
        op.create_table(
            "uas_tracks_core",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("track_key", sa.String(128), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("classification", sa.String(32), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("latitude", sa.Float(), nullable=True),
            sa.Column("longitude", sa.Float(), nullable=True),
            sa.Column("altitude_m", sa.Float(), nullable=True),
            sa.Column("speed_mps", sa.Float(), nullable=True),
            sa.Column("heading_deg", sa.Float(), nullable=True),
            sa.Column("source_count", sa.Integer(), nullable=False),
            sa.Column("sources_json", sa.Text(), nullable=True),
            sa.Column("geofence_state", sa.String(24), nullable=False),
            sa.Column("review_status", sa.String(24), nullable=False),
            sa.Column("first_seen_at", sa.DateTime(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
        )
        op.create_index("ix_uas_track_key", "uas_tracks_core", ["track_key"], unique=True)
        op.create_index("ix_uas_track_last_seen", "uas_tracks_core", ["last_seen_at"])
        op.create_index("ix_uas_track_status", "uas_tracks_core", ["status"])

    if "uas_track_points" not in tables:
        op.create_table(
            "uas_track_points",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("track_id", sa.Integer(), sa.ForeignKey("uas_tracks_core.id"), nullable=False),
            sa.Column("observation_id", sa.Integer(), sa.ForeignKey("uas_observations.id"), nullable=True),
            sa.Column("observed_at", sa.DateTime(), nullable=False),
            sa.Column("latitude", sa.Float(), nullable=True),
            sa.Column("longitude", sa.Float(), nullable=True),
            sa.Column("altitude_m", sa.Float(), nullable=True),
            sa.Column("speed_mps", sa.Float(), nullable=True),
            sa.Column("heading_deg", sa.Float(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=False),
        )
        op.create_index("ix_uas_track_points_track_time", "uas_track_points", ["track_id", "observed_at"])

    if "uas_geofences" not in tables:
        op.create_table(
            "uas_geofences",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("center_latitude", sa.Float(), nullable=False),
            sa.Column("center_longitude", sa.Float(), nullable=False),
            sa.Column("radius_m", sa.Float(), nullable=False),
            sa.Column("severity", sa.String(16), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.String(128), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    if "uas_reviews" not in tables:
        op.create_table(
            "uas_reviews",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("track_id", sa.Integer(), sa.ForeignKey("uas_tracks_core.id"), nullable=False),
            sa.Column("decision", sa.String(24), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("reviewer_uid", sa.String(128), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_uas_reviews_track", "uas_reviews", ["track_id", "reviewed_at"])

def downgrade():
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    for name in ["uas_reviews", "uas_geofences", "uas_track_points", "uas_tracks_core", "uas_observations"]:
        if name in tables:
            op.drop_table(name)
