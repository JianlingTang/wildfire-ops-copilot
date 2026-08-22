from fastapi.testclient import TestClient

import app.services.api_auth as api_auth_module
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


def test_authenticated_admin_email_is_used_as_approval_actor(monkeypatch) -> None:
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "wildfireops-test")
    monkeypatch.setenv("AUTH_ALLOWED_EMAILS", "operator@example.com")
    monkeypatch.setenv("AUTH_ADMIN_EMAILS", "incident-controller@example.com")
    monkeypatch.setattr(api_auth_module, "settings", api_auth_module.settings.__class__())
    monkeypatch.setattr(
        api_auth_module.id_token,
        "verify_firebase_token",
        lambda *args, **kwargs: {
            "user_id": "admin-1",
            "email": "incident-controller@example.com",
            "email_verified": True,
        },
    )
    headers = {"Authorization": "Bearer firebase-id-token"}
    client = TestClient(app)
    run = client.post(
        "/api/runs/manual",
        json={"region_id": "blue_mountains", "region_name": "Blue Mountains"},
        headers=headers,
    )
    run_id = run.json()["run"]["run_id"]
    action = client.post(
        "/api/chat",
        json={"message": "Draft a public advisory for this alert.", "run_id": run_id},
        headers=headers,
    )
    action_id = action.json()["response"]["action"]["action_id"]

    response = client.post(
        f"/api/actions/{action_id}/approve",
        json={"actor": "spoofed_actor"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["approval"]["approved_by"] == "incident-controller@example.com"
    assert store.audit_logs[-1]["actor"] == "incident-controller@example.com"


def test_authenticated_operator_cannot_approve_action(monkeypatch) -> None:
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "wildfireops-test")
    monkeypatch.setenv("AUTH_ALLOWED_EMAILS", "operator@example.com")
    monkeypatch.setenv("AUTH_ADMIN_EMAILS", "incident-controller@example.com")
    monkeypatch.setattr(api_auth_module, "settings", api_auth_module.settings.__class__())
    monkeypatch.setattr(
        api_auth_module.id_token,
        "verify_firebase_token",
        lambda *args, **kwargs: {"user_id": "operator-1", "email": "operator@example.com", "email_verified": True},
    )
    headers = {"Authorization": "Bearer firebase-id-token"}
    client = TestClient(app)
    run = client.post(
        "/api/runs/manual",
        json={"region_id": "blue_mountains", "region_name": "Blue Mountains"},
        headers=headers,
    )
    run_id = run.json()["run"]["run_id"]
    action = client.post(
        "/api/chat",
        json={"message": "Draft a public advisory for this alert.", "run_id": run_id},
        headers=headers,
    )
    action_id = action.json()["response"]["action"]["action_id"]

    response = client.post(
        f"/api/actions/{action_id}/approve",
        json={"actor": "operator@example.com"},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role is required"
