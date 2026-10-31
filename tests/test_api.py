import json

import pytest
from fastapi.testclient import TestClient

from backend import main

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """Keep every test isolated from the user's real database and uploads."""
    test_data = tmp_path / "data"
    test_uploads = test_data / "uploads"
    test_uploads.mkdir(parents=True)

    monkeypatch.setattr(main, "DATA", test_data)
    monkeypatch.setattr(main, "UPLOADS", test_uploads)
    monkeypatch.setattr(main, "DB", test_data / "test_viralsim.db")
    main.init_db()


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


def test_analyze_simulate_report_and_compare():
    video_id = "test-video-regression"

    # Create a minimal video record without requiring a real upload.
    with main.connect() as connection:
        connection.execute(
            """
            INSERT INTO videos
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                video_id,
                "regression-test.mp4",
                "regression-test.mp4",
                1024,
                20.0,
                "Instagram Reels",
                "Technology",
                "Retention",
                None,
                "uploaded",
                json.dumps({"metadata_source": "test fixture"}),
                main.now(),
            ),
        )

    # Analyze the video and verify the limitations are explicit.
    analysis_response = client.post(f"/api/videos/{video_id}/analyze")
    assert analysis_response.status_code == 200

    analysis = analysis_response.json()["analysis"]
    assert analysis["status"] == "metadata_ready"
    assert analysis["timeline"]
    assert analysis["signals"]["semantic_scene_detection"] == "not configured"

    config = {
        "platform": "Instagram Reels",
        "category": "Technology",
        "objective": "Retention",
        "audience_size": 100,
        "rounds": 3,
        "seed": 41,
    }

    run_ids = []

    for seed in (41, 42):
        response = client.post(
            f"/api/videos/{video_id}/simulate",
            json={**config, "seed": seed},
        )
        assert response.status_code == 200, response.text

        run_id = response.json()["run_id"]
        run_ids.append(run_id)

        # TestClient waits for the endpoint's background task to finish.
        run_response = client.get(f"/api/runs/{run_id}")
        assert run_response.status_code == 200
        assert run_response.json()["status"] == "completed"

        report_response = client.get(f"/api/runs/{run_id}/report")
        assert report_response.status_code == 200

        report = report_response.json()
        assert report["mode"] == "heuristic_synthetic_estimate"
        assert report["is_demo_or_heuristic"] is True
        assert report["seed"] == seed
        assert len(report["cohorts"]) == 8
        assert report["recommendations"]

    comparison_response = client.post(
        "/api/compare",
        json={"run_a": run_ids[0], "run_b": run_ids[1]},
    )
    assert comparison_response.status_code == 200, comparison_response.text

    comparison = comparison_response.json()
    assert comparison["run_a"]["run_id"] == run_ids[0]
    assert comparison["run_b"]["run_id"] == run_ids[1]
