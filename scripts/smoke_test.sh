#!/usr/bin/env bash
set -euo pipefail

export GOOGLE_API_KEY="${GOOGLE_API_KEY:-dummy}"
export ELASTIC_MCP_URL="${ELASTIC_MCP_URL:-dummy}"
export FIRESTORE_EMULATOR_HOST="${FIRESTORE_EMULATOR_HOST:-dummy}"
export NASA_FIRMS_API_KEY="${NASA_FIRMS_API_KEY:-dummy}"
export ENVIRONMENT="${ENVIRONMENT:-test}"

"${PYTHON:-python3}" - <<'PY'
from fastapi.testclient import TestClient

from app.main import app
from app.services.firestore_store import store

client = TestClient(app)

run_response = client.post("/api/runs/manual", json={"region_id": "blue_mountains", "region_name": "Blue Mountains"})
run_response.raise_for_status()
run = run_response.json()["run"]
run_id = run["run_id"]
assert run["risk_score"] == 83

events_response = client.get(f"/api/runs/{run_id}/events")
events_response.raise_for_status()
assert events_response.json()["events"]

changed_response = client.post("/api/chat", json={"message": "What changed since yesterday?", "run_id": run_id})
changed_response.raise_for_status()
assert changed_response.json()["intent"] == "CHANGE_EXPLANATION"

what_if_response = client.post("/api/chat", json={"message": "What if wind increases by 20%?", "run_id": run_id})
what_if_response.raise_for_status()
assert what_if_response.json()["intent"] == "WHAT_IF"

draft_response = client.post("/api/chat", json={"message": "Draft a public advisory for this alert.", "run_id": run_id})
draft_response.raise_for_status()
draft = draft_response.json()["response"]
assert draft["approval"]["status"] == "pending_approval"
action_id = draft["action"]["action_id"]

approve_response = client.post(f"/api/actions/{action_id}/approve", json={"actor": "incident_controller"})
approve_response.raise_for_status()
assert approve_response.json()["approval"]["status"] == "approved"
assert store.audit_logs[-1]["event_type"] == "ACTION_APPROVED"

print(f"smoke ok: run={run_id} action={action_id}")
PY
