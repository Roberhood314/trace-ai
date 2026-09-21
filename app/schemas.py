from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class AuthOut(BaseModel):
    token: str
    username: str | None = None
    role: str
    verified: bool = True

class CaseCreate(BaseModel):
    case_code: str = Field(min_length=3, max_length=64)
    title: str = Field(min_length=3, max_length=255)
    legal_reference: str | None = Field(default=None, max_length=255)

class CaseOut(CaseCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    started_at: datetime

class MissingPersonCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    year_of_birth: int | None = Field(default=None, ge=1900, le=2100)
    height_cm: float | None = Field(default=None, ge=30, le=260)
    weight_kg: float | None = Field(default=None, ge=2, le=400)
    appearance: str | None = None
    identifying_features: str | None = None
    permanent_address: str | None = None
    temporary_address: str | None = None

class MissingPersonOut(MissingPersonCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: int

class TimelineEventCreate(BaseModel):
    event_time: datetime
    event_type: str = Field(min_length=2, max_length=64)
    description: str = Field(min_length=2)
    source_type: str | None = Field(default=None, max_length=64)
    source_reference: str | None = Field(default=None, max_length=255)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    confidence: float | None = Field(default=None, ge=0, le=1)

class TimelineEventOut(TimelineEventCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: int

class SearchZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    priority: str = Field(default="medium", pattern="^(low|medium|high)$")
    center_latitude: float = Field(ge=-90, le=90)
    center_longitude: float = Field(ge=-180, le=180)
    radius_m: float = Field(gt=0, le=100000)
    score: float = Field(default=0, ge=0, le=100)
    rationale: str | None = None

class SearchZoneOut(SearchZoneCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: int

class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: int
    person_id: int | None = None
    original_name: str
    media_type: str
    size_bytes: int
    note: str | None = None
    created_at: datetime
    url: str | None = None

class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor: str
    action: str
    resource_type: str
    resource_id: str | None = None
    occurred_at: datetime
    detail: str | None = None

class AISummaryOut(BaseModel):
    case_id: int
    generated_at: datetime
    summary: str
    recommended_checks: list[str]
    zone_order: list[str]
