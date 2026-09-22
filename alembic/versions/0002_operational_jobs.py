"""Add durable operational job queue."""

from alembic import op
import sqlalchemy as sa

revision = "0002_operational_jobs"
down_revision = "0001_adopt_existing_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "operational_jobs" not in inspector.get_table_names():
        op.create_table(
            "operational_jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("job_type", sa.String(length=64), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("run_after", sa.DateTime(), nullable=False),
            sa.Column("locked_at", sa.DateTime(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_operational_jobs_job_type", "operational_jobs", ["job_type"])
        op.create_index("ix_operational_jobs_status", "operational_jobs", ["status"])
        op.create_index("ix_operational_jobs_run_after", "operational_jobs", ["run_after"])
        op.create_index("ix_operational_jobs_created_at", "operational_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_table("operational_jobs")
