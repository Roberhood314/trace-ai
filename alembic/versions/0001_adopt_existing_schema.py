"""Adopt the existing TRACE-AI schema under Alembic control."""

from alembic import op
import sqlalchemy as sa

from app.database import Base
from app import models  # noqa: F401

revision = "0001_adopt_existing_schema"
down_revision = None
branch_labels = None
depends_on = None


def _columns(inspector, table_name: str) -> set[str]:
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(inspector, table_name: str) -> set[str]:
    if table_name not in inspector.get_table_names():
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name) if index.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

    inspector = sa.inspect(bind)
    wanted_columns = _columns(inspector, "wanted_records")
    additions = {
        "source_record_id": sa.Column("source_record_id", sa.String(length=128), nullable=True),
        "status": sa.Column("status", sa.String(length=32), nullable=True, server_default="active"),
        "checksum": sa.Column("checksum", sa.String(length=64), nullable=True),
        "source_updated_at": sa.Column("source_updated_at", sa.DateTime(), nullable=True),
    }
    for name, column in additions.items():
        if name not in wanted_columns:
            op.add_column("wanted_records", column)

    inspector = sa.inspect(bind)
    index_names = _indexes(inspector, "wanted_records")
    desired_indexes = {
        "ix_wanted_records_source_record_id": ["source_record_id"],
        "ix_wanted_records_status": ["status"],
        "ix_wanted_records_checksum": ["checksum"],
    }
    for index_name, columns in desired_indexes.items():
        if index_name not in index_names:
            op.create_index(index_name, "wanted_records", columns, unique=False)

    op.execute(sa.text("UPDATE wanted_records SET status='active' WHERE status IS NULL"))
    Base.metadata.tables["wanted_record_history"].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    pass
