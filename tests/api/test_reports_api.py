from fastapi.testclient import TestClient

from app.main import app


def test_create_and_get_report() -> None:
    client = TestClient(app)
    run = client.post("/api/runs/manual", json={"region_id": "blue_mountains", "region_name": "Blue Mountains"})
    run_id = run.json()["run"]["run_id"]

    created = client.post(f"/api/reports/{run_id}")

    assert created.status_code == 200
    report_id = created.json()["report"]["report_id"]

    fetched = client.get(f"/api/reports/{report_id}")
    assert fetched.status_code == 200
    assert fetched.json()["report"]["run_id"] == run_id
