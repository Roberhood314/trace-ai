from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

IntegrationState = Literal["connected", "degraded", "not_configured", "error"]

INTEGRATIONS = {
    "vision": ("VISION_GATEWAY_URL", "Camera/Vision gateway"),
    "geo": ("GEO_GATEWAY_URL", "Geo/Road gateway"),
    "air": ("UAS_GATEWAY_URL", "UAS sensor gateway"),
    "satellite": ("SATELLITE_GATEWAY_URL", "Satellite provider"),
    "mobility": ("MOBILITY_GATEWAY_URL", "Mobility gateway"),
    "iot": ("IOT_GATEWAY_URL", "IoT gateway"),
    "fusion": ("FUSION_GATEWAY_URL", "Fusion service"),
}

UAS_LAST_EVENT_AT: datetime | None = None
UAS_TRACKS: dict[str, dict] = {}

class UASEvent(BaseModel):
    track_id: str = Field(min_length=1, max_length=128)
    source: Literal["remote_id", "radar", "rf", "eo", "thermal", "acoustic", "gnss", "airspace"]
    timestamp: datetime
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    altitude_m: float | None = Field(default=None, ge=-1000, le=100000)
    speed_mps: float | None = Field(default=None, ge=0, le=1500)
    heading_deg: float | None = Field(default=None, ge=0, le=360)
    classification: Literal["uav", "aircraft", "bird", "unknown"] = "unknown"
    sensor_confidence: float = Field(default=0.5, ge=0, le=1)
    classification_confidence: float = Field(default=0.5, ge=0, le=1)
    source_reference: str | None = Field(default=None, max_length=255)

def _iso(value: datetime | None):
    return value.astimezone(timezone.utc).isoformat() if value else None

def integration_status():
    now = datetime.now(timezone.utc)
    rows = []
    for key, (env_name, label) in INTEGRATIONS.items():
        url = os.getenv(env_name, "").strip()
        configured = bool(url)
        healthy = configured
        last_event = None
        detail = f"{label} chưa cấu hình"
        source_count = 0
        state: IntegrationState = "not_configured"
        if key == "air":
            source_count = len({t.get("source") for t in UAS_TRACKS.values() if t.get("source")})
            last_event = UAS_LAST_EVENT_AT
            gateway_key = bool(os.getenv("TRACE_GATEWAY_KEY", "").strip())
            configured = configured or gateway_key
            if configured and UAS_LAST_EVENT_AT:
                age = (now - UAS_LAST_EVENT_AT.astimezone(timezone.utc)).total_seconds()
                healthy = age <= 60
                state = "connected" if healthy else "degraded"
                detail = "UAS telemetry live" if healthy else "UAS gateway configured; telemetry stale"
            elif configured:
                state = "degraded"
                healthy = False
                detail = "UAS gateway configured; no telemetry received yet"
        elif configured:
            state = "connected"
            detail = f"{label} configured"
        rows.append({
            "id": key,
            "state": state,
            "configured": configured,
            "healthy": healthy,
            "source_count": source_count,
            "last_event_at": _iso(last_event),
            "detail": detail,
        })
    return rows

def ingest_uas_event(event: UASEvent):
    global UAS_LAST_EVENT_AT
    now = datetime.now(timezone.utc)
    UAS_LAST_EVENT_AT = now
    current = UAS_TRACKS.get(event.track_id, {})
    payload = event.model_dump(mode="json")
    payload["received_at"] = now.isoformat()
    payload["status"] = "unverified"
    payload["sources"] = sorted(set((current.get("sources") or []) + [event.source]))
    UAS_TRACKS[event.track_id] = payload
    if len(UAS_TRACKS) > 500:
        oldest = sorted(UAS_TRACKS.items(), key=lambda kv: kv[1].get("received_at", ""))[:100]
        for key, _ in oldest:
            UAS_TRACKS.pop(key, None)
    return UAS_TRACKS[event.track_id]

def recent_uas_tracks(limit: int = 100):
    rows = sorted(UAS_TRACKS.values(), key=lambda x: x.get("received_at", ""), reverse=True)
    return rows[: max(1, min(limit, 500))]
