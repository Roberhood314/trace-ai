import os
from datetime import datetime, timezone

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import WantedRecord
from .wanted_sync import OFFICIAL_WANTED_URL, SOURCE_NAME


def utc_iso(value):
    if not value:
        return datetime.now(timezone.utc).isoformat()
    if getattr(value, "tzinfo", None) is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def public_gateway_status(db: Session) -> dict:
    latest = db.scalar(select(WantedRecord).order_by(WantedRecord.last_seen_at.desc()).limit(1))
    count = len(list(db.scalars(select(WantedRecord.id)).all()))
    return {
        "enabled": True,
        "sources": [
            {
                "id": "bca-wanted-public",
                "name": SOURCE_NAME,
                "kind": "public_official",
                "healthy": count > 0,
                "lastSync": utc_iso(latest.last_seen_at) if latest else None,
                "records": count,
                "sourceUrl": OFFICIAL_WANTED_URL,
            }
        ],
    }


def public_gateway_signals(db: Session, q: str | None = None, limit: int = 50) -> list[dict]:
    limit = max(1, min(int(limit), 100))
    stmt = select(WantedRecord).order_by(WantedRecord.last_seen_at.desc(), WantedRecord.id.desc())
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(
            WantedRecord.full_name.ilike(term),
            WantedRecord.registered_address.ilike(term),
            WantedRecord.offense.ilike(term),
            WantedRecord.warrant_reference.ilike(term),
            WantedRecord.issuing_unit.ilike(term),
        ))
    rows = list(db.scalars(stmt.limit(limit)).all())
    out = []
    for row in rows:
        details = [x for x in [row.offense, row.registered_address, row.warrant_reference, row.issuing_unit] if x]
        out.append({
            "id": f"wanted:{row.id}",
            "title": row.full_name,
            "summary": " · ".join(details[:3]),
            "sourceName": row.source_name,
            "sourceKind": "public_official",
            "observedAt": utc_iso(row.last_seen_at),
            "confidence": 1.0,
            "referenceUrl": row.detail_url or row.source_url,
        })
    return out


async def weather_snapshot(latitude: float, longitude: float) -> dict:
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError("invalid coordinates")
    provider_url = os.getenv("WEATHER_GATEWAY_URL", "").strip()
    if provider_url:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            response = await client.get(provider_url, params={"lat": latitude, "lon": longitude})
            response.raise_for_status()
            data = response.json()
        return {
            "provider": data.get("provider", "authorized-weather-gateway"),
            "observedAt": data.get("observedAt") or datetime.now(timezone.utc).isoformat(),
            "temperatureC": data.get("temperatureC"),
            "precipitationMm": data.get("precipitationMm"),
            "windKph": data.get("windKph"),
            "visibilityKm": data.get("visibilityKm"),
            "condition": data.get("condition"),
        }

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,precipitation,weather_code,wind_speed_10m",
        "hourly": "visibility",
        "forecast_hours": 1,
        "timezone": "auto",
    }
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
        response.raise_for_status()
        data = response.json()
    current = data.get("current") or {}
    hourly = data.get("hourly") or {}
    visibility = None
    values = hourly.get("visibility") or []
    if values:
        try:
            visibility = round(float(values[0]) / 1000, 1)
        except (TypeError, ValueError):
            visibility = None
    return {
        "provider": "Open-Meteo",
        "observedAt": current.get("time") or datetime.now(timezone.utc).isoformat(),
        "temperatureC": current.get("temperature_2m"),
        "precipitationMm": current.get("precipitation"),
        "windKph": current.get("wind_speed_10m"),
        "visibilityKm": visibility,
        "condition": f"WMO {current.get('weather_code')}" if current.get("weather_code") is not None else None,
    }


async def response_units_snapshot() -> list[dict]:
    provider_url = os.getenv("RESPONSE_UNIT_GATEWAY_URL", "").strip()
    if not provider_url:
        return []
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        response = await client.get(provider_url)
        response.raise_for_status()
        payload = response.json()
    rows = payload if isinstance(payload, list) else payload.get("units", [])
    out: list[dict] = []
    for item in rows[:200]:
        try:
            lat = float(item.get("latitude"))
            lon = float(item.get("longitude"))
        except (TypeError, ValueError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        out.append({
            "id": str(item.get("id") or f"unit-{len(out)+1}"),
            "label": str(item.get("label") or item.get("name") or "Đơn vị"),
            "latitude": lat,
            "longitude": lon,
            "available": bool(item.get("available", True)),
            "mode": item.get("mode") if item.get("mode") in {"walk", "vehicle", "motorbike"} else "vehicle",
            "source": "authorized_gateway",
            "updatedAt": item.get("updatedAt") or item.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        })
    return out
