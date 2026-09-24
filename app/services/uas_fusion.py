from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import UASGeofence, UASObservation, UASReview, UASTrack, UASTrackPoint

SOURCE_WEIGHT = {
    "remote_id": 1.00,
    "radar": 0.95,
    "rf": 0.80,
    "eo": 0.72,
    "thermal": 0.78,
    "acoustic": 0.55,
    "gnss": 0.85,
    "airspace": 0.95,
    "mobile_camera": 0.45,
}

def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl/2)**2
    return 2 * r * math.asin(math.sqrt(a))

def _sources(track: UASTrack) -> set[str]:
    try:
        data = json.loads(track.sources_json or "[]")
        return {str(x) for x in data if x}
    except Exception:
        return set()

def _track_for_observation(db: Session, obs: UASObservation) -> UASTrack | None:
    if obs.source_track_id:
        key = f"{obs.source}:{obs.source_track_id}"
        exact = db.scalar(select(UASTrack).where(UASTrack.track_key == key))
        if exact:
            return exact

    if obs.latitude is None or obs.longitude is None:
        return None

    cutoff = obs.observed_at - timedelta(seconds=20)
    recent = list(db.scalars(
        select(UASTrack)
        .where(UASTrack.status == "active", UASTrack.last_seen_at >= cutoff)
        .order_by(UASTrack.last_seen_at.desc())
        .limit(100)
    ).all())

    best = None
    best_distance = None
    for track in recent:
        if track.latitude is None or track.longitude is None:
            continue
        distance = _haversine_m(obs.latitude, obs.longitude, track.latitude, track.longitude)
        if distance > 750:
            continue
        if obs.altitude_m is not None and track.altitude_m is not None and abs(obs.altitude_m - track.altitude_m) > 300:
            continue
        if best_distance is None or distance < best_distance:
            best, best_distance = track, distance
    return best

def _geofence_state(db: Session, lat: float | None, lon: float | None) -> str:
    if lat is None or lon is None:
        return "unknown"
    state = "clear"
    for fence in db.scalars(select(UASGeofence).where(UASGeofence.is_active.is_(True))).all():
        if _haversine_m(lat, lon, fence.center_latitude, fence.center_longitude) <= fence.radius_m:
            if fence.severity == "critical":
                return "critical"
            state = "warning"
    return state

def ingest_observation(
    db: Session,
    *,
    observation_key: str,
    source: str,
    observed_at: datetime,
    created_by: str | None,
    source_track_id: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    altitude_m: float | None = None,
    speed_mps: float | None = None,
    heading_deg: float | None = None,
    observer_latitude: float | None = None,
    observer_longitude: float | None = None,
    observer_heading_deg: float | None = None,
    classification: str = "unknown",
    confidence: float = 0.5,
    metadata: dict | None = None,
) -> tuple[UASObservation, UASTrack | None]:
    existing = db.scalar(select(UASObservation).where(UASObservation.observation_key == observation_key))
    if existing:
        linked = None
        if existing.latitude is not None and existing.longitude is not None:
            point = db.scalar(select(UASTrackPoint).where(UASTrackPoint.observation_id == existing.id))
            if point:
                linked = db.get(UASTrack, point.track_id)
        return existing, linked

    obs = UASObservation(
        observation_key=observation_key,
        source=source,
        source_track_id=source_track_id,
        observed_at=_naive(observed_at),
        received_at=utcnow_naive(),
        latitude=latitude,
        longitude=longitude,
        altitude_m=altitude_m,
        speed_mps=speed_mps,
        heading_deg=heading_deg,
        observer_latitude=observer_latitude,
        observer_longitude=observer_longitude,
        observer_heading_deg=observer_heading_deg,
        classification=classification,
        confidence=max(0.0, min(float(confidence), 1.0)),
        metadata_json=json.dumps(metadata or {}, ensure_ascii=False, default=str),
        created_by=created_by,
    )
    db.add(obs)
    db.flush()

    # Bearing-only camera observations are retained but cannot create a target
    # position until another source provides a range/position estimate.
    if latitude is None or longitude is None:
        db.commit()
        db.refresh(obs)
        return obs, None

    track = _track_for_observation(db, obs)
    if track is None:
        track = UASTrack(
            track_key=f"{source}:{source_track_id}" if source_track_id else f"fusion:{uuid.uuid4().hex[:20]}",
            status="active",
            classification=classification,
            confidence=0.0,
            latitude=latitude,
            longitude=longitude,
            altitude_m=altitude_m,
            speed_mps=speed_mps,
            heading_deg=heading_deg,
            source_count=0,
            sources_json="[]",
            geofence_state="clear",
            review_status="pending",
            first_seen_at=obs.observed_at,
            last_seen_at=obs.observed_at,
            version=1,
        )
        db.add(track)
        db.flush()

    sources = _sources(track)
    sources.add(source)
    weight = SOURCE_WEIGHT.get(source, 0.5)
    weighted_conf = obs.confidence * weight
    prior_weight = max(0.1, track.source_count)
    track.confidence = min(1.0, ((track.confidence * prior_weight) + weighted_conf) / (prior_weight + weight))
    if classification != "unknown" and (track.classification == "unknown" or weighted_conf >= track.confidence):
        track.classification = classification
    track.latitude = latitude
    track.longitude = longitude
    track.altitude_m = altitude_m if altitude_m is not None else track.altitude_m
    track.speed_mps = speed_mps if speed_mps is not None else track.speed_mps
    track.heading_deg = heading_deg if heading_deg is not None else track.heading_deg
    track.source_count = len(sources)
    track.sources_json = json.dumps(sorted(sources), ensure_ascii=False)
    track.geofence_state = _geofence_state(db, latitude, longitude)
    track.last_seen_at = obs.observed_at
    track.version += 1

    db.add(UASTrackPoint(
        track_id=track.id,
        observation_id=obs.id,
        observed_at=obs.observed_at,
        latitude=latitude,
        longitude=longitude,
        altitude_m=altitude_m,
        speed_mps=speed_mps,
        heading_deg=heading_deg,
        confidence=obs.confidence,
    ))
    db.commit()
    db.refresh(obs)
    db.refresh(track)
    return obs, track

def review_track(db: Session, track_id: int, decision: str, reviewer_uid: str, note: str | None = None) -> UASTrack:
    track = db.get(UASTrack, track_id)
    if not track:
        raise KeyError("track not found")
    if decision not in {"verified", "rejected", "needs_review"}:
        raise ValueError("invalid decision")
    track.review_status = decision
    if decision == "rejected":
        track.status = "closed"
    db.add(UASReview(track_id=track.id, decision=decision, note=note, reviewer_uid=reviewer_uid))
    db.commit()
    db.refresh(track)
    return track

def track_snapshot(track: UASTrack) -> dict:
    try:
        sources = json.loads(track.sources_json or "[]")
    except Exception:
        sources = []
    return {
        "id": track.id,
        "track_key": track.track_key,
        "status": track.status,
        "classification": track.classification,
        "confidence": track.confidence,
        "latitude": track.latitude,
        "longitude": track.longitude,
        "altitude_m": track.altitude_m,
        "speed_mps": track.speed_mps,
        "heading_deg": track.heading_deg,
        "source_count": track.source_count,
        "sources": sources,
        "geofence_state": track.geofence_state,
        "review_status": track.review_status,
        "first_seen_at": track.first_seen_at.isoformat() if track.first_seen_at else None,
        "last_seen_at": track.last_seen_at.isoformat() if track.last_seen_at else None,
        "version": track.version,
    }

def fusion_status(db: Session) -> dict:
    tracks = list(db.scalars(select(UASTrack).where(UASTrack.status == "active")).all())
    pending = sum(1 for t in tracks if t.review_status == "pending")
    geofence_alerts = sum(1 for t in tracks if t.geofence_state in {"warning", "critical"})
    return {
        "engine": "TRACE Fusion Core v1",
        "signal_ingest": "operational",
        "track_correlation": "operational",
        "classification": "operational",
        "trajectory": "operational",
        "geofence": "operational",
        "human_review": "operational",
        "active_tracks": len(tracks),
        "pending_review": pending,
        "geofence_alerts": geofence_alerts,
    }
