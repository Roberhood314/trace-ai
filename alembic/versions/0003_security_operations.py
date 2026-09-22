"""Add tamper-evident audit fields and queue lookup index."""

from alembic import op
import sqlalchemy as sa

revision = "0003_security_operations"
down_revision = "0002_operational_jobs"
branch_labels = None
depends_on = None


def _indexes(inspector, table):
    return {item["name"] for item in inspector.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns("audit_events")}
    if "previous_hash" not in columns:
        op.add_column("audit_events", sa.Column("previous_hash", sa.String(length=64), nullable=True))
    if "event_hash" not in columns:
        op.add_column("audit_events", sa.Column("event_hash", sa.String(length=64), nullable=True))
    indexes = _indexes(sa.inspect(bind), "audit_events")
    if "ix_audit_events_previous_hash" not in indexes:
        op.create_index("ix_audit_events_previous_hash", "audit_events", ["previous_hash"])
    if "ix_audit_events_event_hash" not in indexes:
        op.create_index("ix_audit_events_event_hash", "audit_events", ["event_hash"], unique=True)
    job_indexes = _indexes(sa.inspect(bind), "operational_jobs")
    if "ix_operational_jobs_status_run_after" not in job_indexes:
        op.create_index("ix_operational_jobs_status_run_after", "operational_jobs", ["status", "run_after"])


def downgrade() -> None:
    op.drop_index("ix_operational_jobs_status_run_after", table_name="operational_jobs")
    op.drop_index("ix_audit_events_event_hash", table_name="audit_events")
    op.drop_index("ix_audit_events_previous_hash", table_name="audit_events")
    op.drop_column("audit_events", "event_hash")
    op.drop_column("audit_events", "previous_hash")
