from fastapi.testclient import TestClient

from app.main import app


def create_run(client: TestClient) -> str:
    response = client.post("/api/runs/manual", json={"region_id": "blue_mountains", "region_name": "Blue Mountains"})
    return response.json()["run"]["run_id"]


def test_routes_normal_question_to_analyst_path() -> None:
    client = TestClient(app)
    run_id = create_run(client)

    response = client.post("/api/chat", json={"message": "Why is this region high risk?", "run_id": run_id})

    assert response.status_code == 200
    assert response.json()["intent"] == "RISK_EXPLANATION"
    assert response.json()["response"]["status"] == "success"


def test_analysis_command_creates_run_report_trace_and_returns_demo_mode() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={
            "message": "Analyze the most active hotspot region in Australia and generate today's report.",
            "region_id": "live_australia",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "ANALYZE_AND_REPORT"
    assert payload["mode"] == "demo"
    assert payload["response"]["mode"] == "demo"
    assert payload["run"]["status"] == "completed"
    assert payload["run"]["region_id"] == "live_qld_demo_cluster"
    assert payload["report"]["title"] == "Daily Wildfire Operations Brief"
    assert "Elastic MCP demo evidence" in payload["response"]["answer"]
    assert payload["run"]["evidence"]["region_context"]["selection_mode"] == "demo_auto_live_hotspot"

    events = client.get(f"/api/runs/{payload['run']['run_id']}/events")
    assert events.status_code == 200
    assert any(event["step"] == "query_elastic_mcp_evidence" for event in events.json()["events"])
    assert any(event["step"] == "select_live_hotspot_region" for event in events.json()["events"])


def test_analysis_command_accepts_selected_state_and_radius() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={
            "message": "Analyze this selected hotspot area and generate today's report.",
            "region_id": "state_nt",
            "region_name": "Northern Territory hotspot focus",
            "aoi": {"center": [-12.4513, 132.9192], "radius_km": 100},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["region_id"] == "state_nt"
    assert payload["run"]["region_name"] == "Northern Territory hotspot focus"
    assert payload["run"]["evidence"]["region_context"]["state"] == "NT"
    assert payload["run"]["evidence"]["region_context"]["center"] == [-12.4513, 132.9192]
    assert payload["run"]["evidence"]["region_context"]["radius_km"] == 100
    assert payload["run"]["evidence"]["region_context"]["selection_mode"] == "selected_aoi"


def test_routes_what_if_question_to_what_if_path() -> None:
    client = TestClient(app)
    run_id = create_run(client)

    response = client.post(
        "/api/chat",
        json={"message": "What if wind speed increases by 20% tomorrow?", "run_id": run_id},
    )

    assert response.status_code == 200
    assert response.json()["intent"] == "WHAT_IF"
    scenario_score = response.json()["response"]["scenario"]["risk_score"]
    baseline_score = response.json()["response"]["baseline"]["risk_score"]
    assert scenario_score >= baseline_score


def test_focused_aoi_question_without_run_returns_contextual_answer() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={
            "message": "Which area should we inspect first?",
            "region_id": "state_wa",
            "region_name": "Western Australia hotspot cluster focus",
            "aoi": {"center": [-16.12, 126.35], "radius_km": 50},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "OPERATIONAL_PRIORITIZATION"
    assert payload["response"]["status"] == "success"
    assert "Western Australia hotspot cluster focus" in payload["response"]["answer"]
    assert payload["response"]["context"]["source"] == "focused_aoi_context"


def test_focused_aoi_what_if_without_run_returns_qualitative_answer() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={
            "message": "What if wind increases by 20%?",
            "region_id": "state_wa",
            "region_name": "Western Australia hotspot cluster focus",
            "aoi": {"center": [-16.12, 126.35], "radius_km": 50},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "WHAT_IF"
    assert payload["response"]["status"] == "success"
    assert payload["response"]["scenario"]["requires_analysis_for_score"] is True


def test_routes_action_command_to_pending_approval() -> None:
    client = TestClient(app)
    run_id = create_run(client)

    response = client.post("/api/chat", json={"message": "Draft a public advisory for this alert.", "run_id": run_id})

    assert response.status_code == 200
    assert response.json()["intent"] == "ACTION_COMMAND"
    assert response.json()["response"]["action"]["status"] == "pending_approval"
    assert response.json()["response"]["approval"]["status"] == "pending_approval"


def test_hotspot_visualization_command_returns_downloadable_layers() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={
            "message": "Create a hotspot heatmap and contour visualization for this AOI.",
            "region_id": "state_nt",
            "region_name": "Northern Territory hotspot cluster focus",
            "aoi": {"center": [-12.4513, 132.9192], "radius_km": 50},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "HOTSPOT_VISUALIZATION"
    visualization = payload["response"]["visualization"]
    assert visualization["heatmap"]["cells"]
    assert len(visualization["contours"]["features"]) == 3
    assert visualization["downloads"]["json_filename"].endswith(".json")
    assert "Satellite hotspots indicate thermal anomalies" in visualization["interpretation"]["caveat"]


def test_monitor_task_command_creates_active_task() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={
            "message": "Create a monitor task for this state every 10 minutes.",
            "region_id": "state_nt",
            "region_name": "Northern Territory hotspot cluster focus",
            "aoi": {"center": [-12.4513, 132.9192], "radius_km": 50},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "MONITOR_TASK"
    task = payload["response"]["monitor_task"]
    assert task["status"] == "active"
    assert task["interval_minutes"] == 10
    assert task["region_name"] == "Northern Territory hotspot cluster focus"

    tasks_response = client.get("/api/monitor-tasks")
    assert tasks_response.status_code == 200
    assert tasks_response.json()["monitor_tasks"][0]["task_id"] == task["task_id"]


def test_action_command_does_not_execute_external_action_directly() -> None:
    client = TestClient(app)
    run_id = create_run(client)

    response = client.post("/api/chat", json={"message": "Draft an email to emergency services.", "run_id": run_id})

    assert response.status_code == 200
    assert response.json()["response"]["action"]["status"] == "pending_approval"
    assert "requires human approval" in response.json()["response"]["safety_note"]
