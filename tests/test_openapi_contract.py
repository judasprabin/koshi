from fastapi.testclient import TestClient

from koshi.main import app


def test_openapi_schema_lists_this_slices_paths():
    client = TestClient(app)
    response = client.get("/v1/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert "/v1/occupations/{code}" in schema["paths"]
    assert "/v1/occupations" in schema["paths"]
    assert "/v1/healthz" in schema["paths"]
