from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class CaseCreate(BaseModel):
    case_code: str
    title: str
    legal_reference: str | None = None

class CaseOut(CaseCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    started_at: datetime

class MissingPersonCreate(BaseModel):
    full_name: str
    year_of_birth: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
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
    event_type: str
    description: str
    source_type: str | None = None
    source_reference: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    confidence: float | None = Field(default=None, ge=0, le=1)

class TimelineEventOut(TimelineEventCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: int

class SearchZoneCreate(BaseModel):
    name: str
    priority: str = "medium"
    center_latitude: float = Field(ge=-90, le=90)
    center_longitude: float = Field(ge=-180, le=180)
    radius_m: float = Field(gt=0)
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
