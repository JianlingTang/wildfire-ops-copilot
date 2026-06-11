from fastapi.testclient import TestClient

from app.main import app


def test_manual_run_creates_run_emits_trace_events_and_stores_result() -> None:
    client = TestClient(app)

    response = client.post("/api/runs/manual", json={"region_id": "blue_mountains", "region_name": "Blue Mountains"})

    assert response.status_code == 200
    payload = response.json()
    run_id = payload["run"]["run_id"]
    assert payload["run"]["status"] == "completed"
    assert isinstance(payload["run"]["risk_score"], int)
    assert payload["report"]["run_id"] == run_id

    events_response = client.get(f"/api/runs/{run_id}/events")
    assert events_response.status_code == 200
    events = events_response.json()["events"]
    assert any(event["step"] == "compute_risk_score" for event in events)


def test_get_run_returns_stored_run() -> None:
    client = TestClient(app)
    created = client.post("/api/runs/manual", json={"region_id": "blue_mountains", "region_name": "Blue Mountains"})
    run_id = created.json()["run"]["run_id"]

    response = client.get(f"/api/runs/{run_id}")

    assert response.status_code == 200
    assert response.json()["run"]["run_id"] == run_id
