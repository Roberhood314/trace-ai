"""Performance indexes for wanted intelligence.

Revision ID: 0004_wanted_performance
Revises: 0003_security_operations
Create Date: 2026-09-24
"""
from alembic import op

revision = "0004_wanted_performance"
down_revision = "0003_security_operations"
branch_labels = None
depends_on = None

def upgrade():
    op.create_index("ix_wanted_records_status_last_seen", "wanted_records", ["status", "last_seen_at"])
    op.create_index("ix_wanted_records_source_updated_at", "wanted_records", ["source_updated_at"])
    op.create_index("ix_wanted_records_warrant_reference", "wanted_records", ["warrant_reference"])
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute("CREATE INDEX IF NOT EXISTS ix_wanted_records_full_name_trgm ON wanted_records USING gin (full_name gin_trgm_ops)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_wanted_records_address_trgm ON wanted_records USING gin (registered_address gin_trgm_ops)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_wanted_records_offense_trgm ON wanted_records USING gin (offense gin_trgm_ops)")

def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_wanted_records_offense_trgm")
        op.execute("DROP INDEX IF EXISTS ix_wanted_records_address_trgm")
        op.execute("DROP INDEX IF EXISTS ix_wanted_records_full_name_trgm")
    op.drop_index("ix_wanted_records_warrant_reference", table_name="wanted_records")
    op.drop_index("ix_wanted_records_source_updated_at", table_name="wanted_records")
    op.drop_index("ix_wanted_records_status_last_seen", table_name="wanted_records")
