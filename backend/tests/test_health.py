from fastapi.testclient import TestClient

from toonopt.main import app


def test_health():
    r = TestClient(app).get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True
