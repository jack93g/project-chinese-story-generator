from fastapi.testclient import TestClient

from story_generator.api.app import create_app


def test_health_check_reports_an_available_application():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
