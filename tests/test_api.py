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


def test_public_wanted_page_and_stats():
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


def test_integration_health_and_uas_gateway(monkeypatch):
    monkeypatch.setenv("TRACE_GATEWAY_KEY", "test-gateway-key")
    status = client.get("/public/integrations/status")
    assert status.status_code == 200
    rows = status.json()
    assert any(row["id"] == "air" for row in rows)

    event = {
        "track_id": "test-uav-1",
        "source": "remote_id",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latitude": 10.7,
        "longitude": 106.6,
        "altitude_m": 120,
        "speed_mps": 12,
        "heading_deg": 90,
        "classification": "uav",
        "sensor_confidence": 0.9,
        "classification_confidence": 0.8,
    }
    denied = client.post("/integrations/uas/events", json=event)
    assert denied.status_code == 401
    accepted = client.post("/integrations/uas/events", json=event, headers={"X-TRACE-Gateway-Key": "test-gateway-key"})
    assert accepted.status_code == 200
    tracks = client.get("/uas/tracks", headers=ANALYST)
    assert tracks.status_code == 200
    assert tracks.json()["items"][0]["track_id"] == "test-uav-1"


def test_device_pairing_and_uas_ingestion():
    registered = client.post("/devices/register", headers=ADMIN, json={
        "name": "Test Remote ID Receiver",
        "integration_id": "air",
        "platform": "gateway",
        "capabilities": ["remote_id", "radar"],
    })
    assert registered.status_code == 200, registered.text
    device = registered.json()
    assert device["device_id"].startswith("dev_")
    assert len(device["device_token"]) >= 24

    auth = {
        "Authorization": f"Bearer {device['device_token']}",
        "X-TRACE-Device-ID": device["device_id"],
    }
    heartbeat = client.post("/device/heartbeat", headers=auth, json={
        "device_id": device["device_id"],
        "platform": "gateway",
        "version": "1.0",
        "capabilities": ["remote_id", "radar"],
    })
    assert heartbeat.status_code == 200, heartbeat.text

    event = client.post("/device/uas/events", headers=auth, json={
        "track_id": "uas-device-test",
        "source": "remote_id",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latitude": 10.8,
        "longitude": 106.7,
        "altitude_m": 100,
        "speed_mps": 10,
        "heading_deg": 180,
        "classification": "uav",
        "sensor_confidence": 0.9,
        "classification_confidence": 0.8,
    })
    assert event.status_code == 200, event.text
    assert event.json()["device_id"] == device["device_id"]

    forbidden = client.post("/device/uas/events", headers=auth, json={
        "track_id": "uas-device-test-2",
        "source": "thermal",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "classification": "unknown",
        "sensor_confidence": 0.5,
        "classification_confidence": 0.5,
    })
    assert forbidden.status_code == 403


def test_province_reorganization_mapping():
    from app.main import _province_from_address
    assert _province_from_address("TP. Tân An, Long An") == "Tây Ninh"
    assert _province_from_address("TP. Thủ Dầu Một, Bình Dương") == "TP. Hồ Chí Minh"
    assert _province_from_address("TP. Vũng Tàu, Bà Rịa - Vũng Tàu") == "TP. Hồ Chí Minh"
    assert _province_from_address("TP. Đồng Xoài, Bình Phước") == "Đồng Nai"
    assert _province_from_address("TP. Nam Định, Nam Định") == "Ninh Bình"
    assert _province_from_address("TP. Bắc Giang, Bắc Giang") == "Bắc Ninh"
    assert _province_from_address("TP. Hà Giang, Hà Giang") == "Tuyên Quang"
    assert _province_from_address("TP. Huế, Thừa Thiên Huế") == "Huế"


def test_pi_auth_cors_preflight():
    headers = {
        "Origin": "https://traceai12345.pinet.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    response = client.options("/auth/pi/verify", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://traceai12345.pinet.com"
    assert "POST" in response.headers.get("access-control-allow-methods", "")

def test_pi_auth_cors_rejects_unknown_origin():
    headers = {
        "Origin": "https://example.invalid",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    response = client.options("/auth/pi/verify", headers=headers)
    assert response.status_code == 400


def test_uas_user_simulation_mode():
    denied = client.post("/uas/test/start", headers=VIEWER, json={
        "center_latitude": 10.77,
        "center_longitude": 106.70,
        "tracks": 2,
        "duration_seconds": 10,
    })
    assert denied.status_code == 403

    started = client.post("/uas/test/start", headers=ANALYST, json={
        "center_latitude": 10.77,
        "center_longitude": 106.70,
        "tracks": 2,
        "duration_seconds": 10,
    })
    assert started.status_code == 200, started.text
    assert started.json()["mode"] == "simulation"
    assert started.json()["warning"].startswith("SIMULATION ONLY")

    import time
    time.sleep(1.2)
    tracks = client.get("/uas/tracks?include_simulation=true", headers=ANALYST)
    assert tracks.status_code == 200, tracks.text
    sim = [x for x in tracks.json()["items"] if x.get("simulation")]
    assert len(sim) >= 1
    assert all(x.get("status") == "simulation" for x in sim)

    real_only = client.get("/uas/tracks", headers=ANALYST)
    assert real_only.status_code == 200
    assert all(not x.get("simulation") for x in real_only.json()["items"])

    stopped = client.post("/uas/test/stop", headers=ANALYST)
    assert stopped.status_code == 200, stopped.text
    after = client.get("/uas/tracks?include_simulation=true", headers=ANALYST)
    assert all(not x.get("simulation") for x in after.json()["items"])
