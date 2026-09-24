from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Literal

import httpx
from pydantic import BaseModel, Field

IntegrationState = Literal["connected", "degraded", "not_configured", "error"]
IntegrationId = Literal["vision", "geo", "air", "satellite", "mobility", "iot", "fusion"]

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
DEVICE_HEARTBEATS: dict[tuple[str, str], dict] = {}
SIM_UAS_TRACKS: dict[str, dict] = {}

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

class ConnectorHeartbeat(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    platform: Literal["windows", "linux", "macos", "android", "ios", "gateway", "embedded"]
    version: str | None = Field(default=None, max_length=64)
    capabilities: list[str] = Field(default_factory=list, max_length=32)

def _iso(value: datetime | None):
    return value.astimezone(timezone.utc).isoformat() if value else None

def ingest_heartbeat(integration_id: str, heartbeat: ConnectorHeartbeat):
    if integration_id not in INTEGRATIONS:
        raise ValueError("unknown integration")
    now = datetime.now(timezone.utc)
    payload = heartbeat.model_dump(mode="json")
    payload["integration_id"] = integration_id
    payload["last_seen_at"] = now.isoformat()
    DEVICE_HEARTBEATS[(integration_id, heartbeat.device_id)] = payload
    return payload

def _live_heartbeats(integration_id: str, max_age_seconds: int = 90):
    now = datetime.now(timezone.utc)
    rows = []
    for (iid, _), item in DEVICE_HEARTBEATS.items():
        if iid != integration_id:
            continue
        try:
            seen = datetime.fromisoformat(item["last_seen_at"])
        except Exception:
            continue
        if (now - seen.astimezone(timezone.utc)).total_seconds() <= max_age_seconds:
            rows.append(item)
    return rows

async def integration_status():
    now = datetime.now(timezone.utc)
    rows = []
    async with httpx.AsyncClient(timeout=2.5, follow_redirects=True) as client:
        for key, (env_name, label) in INTEGRATIONS.items():
            url = os.getenv(env_name, "").strip()
            token = os.getenv(f"{key.upper()}_GATEWAY_TOKEN", "").strip()
            heartbeats = _live_heartbeats(key)
            configured = bool(url or heartbeats or (key == "air" and os.getenv("TRACE_GATEWAY_KEY", "").strip()))
            healthy = False
            last_event = None
            source_count = len(heartbeats)
            detail = f"{label} chưa cấu hình"
            state: IntegrationState = "not_configured"

            if key == "air" and UAS_LAST_EVENT_AT:
                last_event = UAS_LAST_EVENT_AT
                age = (now - UAS_LAST_EVENT_AT.astimezone(timezone.utc)).total_seconds()
                if age <= 60:
                    healthy = True
                    state = "connected"
                    detail = "UAS telemetry live"
                else:
                    state = "degraded"
                    detail = "UAS gateway configured; telemetry stale"
                source_count = max(source_count, len({t.get("source") for t in UAS_TRACKS.values() if t.get("source")}))

            if url:
                headers = {"Accept": "application/json"}
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                try:
                    response = await client.get(url, headers=headers)
                    if response.status_code < 400:
                        healthy = True
                        state = "connected"
                        detail = f"{label} health probe OK ({response.status_code})"
                    else:
                        state = "error"
                        detail = f"{label} health probe HTTP {response.status_code}"
                except httpx.HTTPError as exc:
                    if not healthy:
                        state = "error"
                    detail = f"{label} health probe failed: {exc.__class__.__name__}"
            elif heartbeats and not healthy:
                healthy = True
                state = "connected"
                latest = max(datetime.fromisoformat(x["last_seen_at"]) for x in heartbeats)
                last_event = latest
                detail = f"{label} connected via device heartbeat"
            elif configured and state == "not_configured":
                state = "degraded"
                detail = f"{label} configured; waiting for live heartbeat/data"

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

def set_simulated_uas_track(track_id: str, payload: dict):
    item = dict(payload)
    item["track_id"] = track_id
    item["simulation"] = True
    item["status"] = "simulation"
    item["received_at"] = datetime.now(timezone.utc).isoformat()
    SIM_UAS_TRACKS[track_id] = item
    return item

def clear_simulated_uas_tracks():
    count = len(SIM_UAS_TRACKS)
    SIM_UAS_TRACKS.clear()
    return count

def recent_uas_tracks(limit: int = 100, include_simulation: bool = False):
    rows = list(UAS_TRACKS.values())
    if include_simulation:
        rows += list(SIM_UAS_TRACKS.values())
    rows = sorted(rows, key=lambda x: x.get("received_at", ""), reverse=True)
    return rows[: max(1, min(limit, 500))]
