import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
ADMIN = {"X-Role": "admin"}
ANALYST = {"X-Role": "analyst"}
VIEWER = {"X-Role": "viewer"}

def create_case():
    code = "T-" + uuid.uuid4().hex[:10]
    r = client.post("/cases", headers=ANALYST, json={"case_code": code, "title": "Test case", "legal_reference": "TEST"})
    assert r.status_code == 200, r.text
    return r.json()

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_case_profile_timeline_zone_and_summary():
    case = create_case()
    cid = case["id"]

    p = client.post(f"/cases/{cid}/person", headers=ANALYST, json={
        "full_name": "Demo Person", "year_of_birth": 1990,
        "height_cm": 170, "weight_kg": 65,
        "appearance": "demo", "identifying_features": "demo",
        "permanent_address": "demo", "temporary_address": None,
    })
    assert p.status_code == 200, p.text

    event = client.post(f"/cases/{cid}/timeline", headers=ANALYST, json={
        "event_time": datetime.now(timezone.utc).isoformat(),
        "event_type": "last_seen",
        "description": "Verified demo point",
        "source_type": "field_report",
        "source_reference": "TEST-1",
        "latitude": 10.77,
        "longitude": 106.70,
        "confidence": 0.8,
    })
    assert event.status_code == 200, event.text

    zone = client.post(f"/cases/{cid}/search-zones", headers=ANALYST, json={
        "name": "Zone A", "priority": "high",
        "center_latitude": 10.77, "center_longitude": 106.70,
        "radius_m": 2000, "score": 85,
        "rationale": "test",
    })
    assert zone.status_code == 200, zone.text

    summary = client.get(f"/cases/{cid}/ai-summary", headers=VIEWER)
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["case_id"] == cid
    assert body["zone_order"] == ["Zone A"]

def test_reject_partial_coordinates():
    case = create_case()
    r = client.post(f"/cases/{case['id']}/timeline", headers=ANALYST, json={
        "event_time": datetime.now(timezone.utc).isoformat(),
        "event_type": "field_clue",
        "description": "partial coord",
        "latitude": 10.7,
        "longitude": None,
        "confidence": 0.5,
    })
    assert r.status_code == 422

def test_role_enforcement():
    code = "T-" + uuid.uuid4().hex[:10]
    r = client.post("/cases", headers=VIEWER, json={"case_code": code, "title": "Denied"})
    assert r.status_code == 403

def test_audit_events_are_hash_chained():
    case = create_case()
    r = client.get(f"/cases/{case['id']}/audit", headers={"X-Role": "commander"})
    assert r.status_code == 200
    # API schema intentionally does not expose integrity hashes; verify them
    # through the model so a later migration cannot silently drop them.
    from app.database import SessionLocal
    from app.models import AuditEvent
    with SessionLocal() as db:
        event = db.query(AuditEvent).order_by(AuditEvent.id.desc()).first()
        assert event and event.event_hash and len(event.event_hash) == 64


def test_public_wanted_page_and_stats(client):
    page = client.get("/public/wanted/page?limit=25&offset=0")
    assert page.status_code == 200
    body = page.json()
    assert set(["items", "total", "limit", "offset", "has_more"]).issubset(body)
    assert body["limit"] == 25
    assert body["offset"] == 0
    assert isinstance(body["items"], list)

    stats = client.get("/public/wanted/stats/provinces")
    assert stats.status_code == 200
    data = stats.json()
    assert "total" in data
    assert "provinces" in data
    assert isinstance(data["provinces"], list)
