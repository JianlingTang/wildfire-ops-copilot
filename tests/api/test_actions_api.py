from fastapi.testclient import TestClient

from app.main import app
from app.services.firestore_store import store


def create_action(client: TestClient) -> str:
    run = client.post("/api/runs/manual", json={"region_id": "blue_mountains", "region_name": "Blue Mountains"})
    run_id = run.json()["run"]["run_id"]
    action = client.post("/api/chat", json={"message": "Draft a public advisory for this alert.", "run_id": run_id})
    return action.json()["response"]["action"]["action_id"]


def test_approve_action_validates_approval_and_writes_audit_log() -> None:
    client = TestClient(app)
    action_id = create_action(client)

    response = client.post(f"/api/actions/{action_id}/approve", json={"actor": "incident_controller"})

    assert response.status_code == 200
    assert response.json()["action"]["status"] == "approved"
    assert response.json()["approval"]["status"] == "approved"
    assert store.audit_logs[-1]["event_type"] == "ACTION_APPROVED"
    assert store.agent_events[-1].agent_type == "approval"
    assert store.agent_events[-1].message == "Public advisory action approved."


def test_reject_action_marks_rejected_and_does_not_execute_action() -> None:
    client = TestClient(app)
    action_id = create_action(client)

    response = client.post(f"/api/actions/{action_id}/reject", json={"actor": "incident_controller"})

    assert response.status_code == 200
    assert response.json()["action"]["status"] == "rejected"
    assert store.actions[action_id].status == "rejected"
    assert store.audit_logs[-1]["event_type"] == "ACTION_REJECTED"
    assert store.agent_events[-1].agent_type == "approval"
    assert store.agent_events[-1].message == "Public advisory action rejected."
