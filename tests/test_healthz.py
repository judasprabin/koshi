from fastapi.testclient import TestClient
from koshi.main import app


def test_healthz_returns_ok():
    client = TestClient(app)
    response = client.get("/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
