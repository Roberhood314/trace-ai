from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_security_headers_are_present():
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers.get("x-frame-options") is None
    csp = response.headers["content-security-policy"]
    assert "frame-ancestors 'self'" in csp
    assert "https://sandbox.minepi.com" in csp
