from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_personas_endpoint():
    response = client.get("/api/personas")
    assert response.status_code == 200

    personas = response.json()["personas"]
    assert len(personas) == 8
    assert all(persona.get("id") for persona in personas)
    assert all(persona.get("name") for persona in personas)


def test_video_library_endpoint():
    response = client.get("/api/videos")
    assert response.status_code == 200
    assert isinstance(response.json()["videos"], list)


def test_simulation_history_endpoint():
    response = client.get("/api/runs")
    assert response.status_code == 200
    assert isinstance(response.json()["runs"], list)
