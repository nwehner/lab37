import uuid

from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_route_stubs_registered() -> None:
    with TestClient(app) as client:
        assert client.get("/orders").status_code == 200
        assert client.get("/ingestion/runs").status_code == 200
        # Dispatch (plan phase 6) is still an unimplemented stub.
        assert client.post(f"/orders/{uuid.uuid4()}/dispatch").status_code == 501
