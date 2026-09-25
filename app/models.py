from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

def utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    pi_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class AccountDeletionRequest(Base):
    __tablename__ = "account_deletion_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    pi_username: Mapped[str] = mapped_column(String(128), index=True)
    contact_email: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    request_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class Case(Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="open")
    legal_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

class MissingPerson(Base):
    __tablename__ = "missing_persons"
    __table_args__ = (UniqueConstraint("case_id", name="uq_missing_person_case"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    year_of_birth: Mapped[int | None] = mapped_column(nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    appearance: Mapped[str | None] = mapped_column(Text, nullable=True)
    identifying_features: Mapped[str | None] = mapped_column(Text, nullable=True)
    permanent_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    temporary_address: Mapped[str | None] = mapped_column(Text, nullable=True)

class TimelineEvent(Base):
    __tablename__ = "timeline_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

class SearchZone(Base):
    __tablename__ = "search_zones"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    center_latitude: Mapped[float] = mapped_column(Float)
    center_longitude: Mapped[float] = mapped_column(Float)
    radius_m: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float, default=0)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(128))
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)

class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("missing_persons.id"), nullable=True, index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    media_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column()
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)

class WantedRecord(Base):
    __tablename__ = "wanted_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    source_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), index=True)
    birth_year: Mapped[int | None] = mapped_column(nullable=True)
    registered_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    parents: Mapped[str | None] = mapped_column(Text, nullable=True)
    offense: Mapped[str | None] = mapped_column(Text, nullable=True)
    warrant_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issuing_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    danger_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_url: Mapped[str] = mapped_column(Text)
    source_name: Mapped[str] = mapped_column(String(255), default="Cổng thông tin truy nã - Bộ Công an")
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

class WantedRecordHistory(Base):
    __tablename__ = "wanted_record_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    wanted_record_id: Mapped[int | None] = mapped_column(ForeignKey("wanted_records.id"), nullable=True, index=True)
    source_key: Mapped[str] = mapped_column(String(255), index=True)
    change_type: Mapped[str] = mapped_column(String(32))
    old_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)


class OperationalJob(Base):
    __tablename__ = "operational_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    run_after: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class ConnectorDevice(Base):
    __tablename__ = "connector_devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    integration_id: Mapped[str] = mapped_column(String(32), index=True)
    platform: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    capabilities_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class UASObservation(Base):
    __tablename__ = "uas_observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    observation_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    source_track_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    observer_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    observer_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    observer_heading_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

class UASTrack(Base):
    __tablename__ = "uas_tracks_core"
    id: Mapped[int] = mapped_column(primary_key=True)
    track_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    classification: Mapped[str] = mapped_column(String(32), default="unknown", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_count: Mapped[int] = mapped_column(default=0)
    sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    geofence_state: Mapped[str] = mapped_column(String(24), default="clear", index=True)
    review_status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)
    version: Mapped[int] = mapped_column(default=1)

class UASTrackPoint(Base):
    __tablename__ = "uas_track_points"
    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("uas_tracks_core.id"), index=True)
    observation_id: Mapped[int | None] = mapped_column(ForeignKey("uas_observations.id"), nullable=True, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    altitude_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)

class UASGeofence(Base):
    __tablename__ = "uas_geofences"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    center_latitude: Mapped[float] = mapped_column(Float)
    center_longitude: Mapped[float] = mapped_column(Float)
    radius_m: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(16), default="warning")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

class UASReview(Base):
    __tablename__ = "uas_reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("uas_tracks_core.id"), index=True)
    decision: Mapped[str] = mapped_column(String(24), index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_uid: Mapped[str] = mapped_column(String(128), index=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)
