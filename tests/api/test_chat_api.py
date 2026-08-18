from fastapi.testclient import TestClient

from app.main import app
from app.services.firestore_store import store


def create_run(client: TestClient) -> str:
    response = client.post("/api/runs/manual", json={"region_id": "blue_mountains", "region_name": "Blue Mountains"})
    return response.json()["run"]["run_id"]


def create_selected_analysis(client: TestClient) -> dict:
    response = client.post(
        "/api/chat",
        json={
            "message": "Analyze this selected hotspot area and generate today's report.",
            "region_id": "state_nt",
            "region_name": "Northern Territory hotspot cluster focus",
            "aoi": {"center": [-12.4513, 132.9192], "radius_km": 50},
        },
    )
    return response.json()


def test_unrelated_question_is_blocked_before_conversation_or_llm() -> None:
    client = TestClient(app)

    response = client.post("/api/chat", json={"message": "Write a wedding poem about Paris."})

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "OUT_OF_SCOPE"
    assert payload["response"]["status"] == "blocked"
    assert payload["response"]["llm_called"] is False
    assert not store.conversations


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
    assert payload["trace_id"].startswith("trace_")
    assert payload["response"]["mode"] == "demo"
    assert payload["conversation_id"].startswith("conv_")
    assert len(payload["messages"]) == 2
    assert payload["run"]["status"] == "completed"
    assert payload["run"]["region_id"] == "live_qld_demo_cluster"
    assert payload["report"]["title"] == "Daily Wildfire Operations Brief"
    assert "Elastic MCP demo evidence" in payload["response"]["answer"]
    assert payload["run"]["evidence"]["region_context"]["selection_mode"] == "demo_auto_live_hotspot"

    events = client.get(f"/api/runs/{payload['run']['run_id']}/events")
    assert events.status_code == 200
    assert any(event["step"] == "query_elastic_mcp_evidence" for event in events.json()["events"])
    assert any(event["step"] == "select_live_hotspot_region" for event in events.json()["events"])

    agent_events = client.get("/api/agent-events/recent")
    assert agent_events.status_code == 200
    event_messages = [event["message"] for event in agent_events.json()["events"]]
    assert any("Intent classified: ANALYZE_AND_REPORT" in message for message in event_messages)
    assert any("Elastic MCP Tool" in message for message in event_messages)


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
    assert len(payload["run"]["evidence"]["risk_timeseries"]["points"]) == 11


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


def test_focused_aoi_question_without_run_requires_analysis_first() -> None:
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
    assert payload["response"]["status"] == "must_run_analysis"
    assert payload["trace_id"].startswith("trace_")
    assert payload["requires_analysis"] is True
    assert payload["response"]["tool_trace"][0]["did"] == "Blocked before workflow tool calls."

    agent_events = client.get("/api/agent-events/recent")
    assert any(event["status"] == "blocked" for event in agent_events.json()["events"])


def test_focused_aoi_what_if_without_run_requires_analysis_first() -> None:
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
    assert payload["response"]["status"] == "must_run_analysis"
    assert payload["requires_analysis"] is True


def test_risk_trend_without_run_requires_analysis_first() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={
            "message": "Show the risk trend for this AOI.",
            "region_id": "state_wa",
            "region_name": "Western Australia hotspot cluster focus",
            "aoi": {"center": [-16.12, 126.35], "radius_km": 50},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "RISK_TREND"
    assert payload["response"]["status"] == "must_run_analysis"
    assert payload["requires_analysis"] is True


def test_risk_trend_after_analysis_returns_points() -> None:
    client = TestClient(app)
    analysis = create_selected_analysis(client)

    response = client.post(
        "/api/chat",
        json={
            "message": "Show the risk trend for this AOI.",
            "conversation_id": analysis["conversation_id"],
            "run_id": analysis["run"]["run_id"],
            "region_id": "state_nt",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "RISK_TREND"
    trend = payload["response"]["risk_trend"]
    assert len(trend["points"]) == 11
    assert {point["type"] for point in trend["points"]} == {"historical", "current", "forecast"}
    assert trend["preview"]["data_url"].startswith("data:image/png;base64,")
    assert trend["downloads"]["png_filename"].endswith(".png")


def test_prediction_after_analysis_returns_forecast_points_and_chart() -> None:
    client = TestClient(app)
    analysis = create_selected_analysis(client)

    response = client.post(
        "/api/chat",
        json={
            "message": "Predict wildfire risk for the next few days.",
            "conversation_id": analysis["conversation_id"],
            "run_id": analysis["run"]["run_id"],
            "region_id": "state_nt",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "RISK_PREDICTION"
    trend = payload["response"]["risk_trend"]
    assert len(trend["prediction"]["forecast_points"]) == 5
    assert trend["preview"]["data_url"].startswith("data:image/png;base64,")


def test_routes_action_command_to_pending_approval() -> None:
    client = TestClient(app)
    run_id = create_run(client)

    response = client.post("/api/chat", json={"message": "Draft a public advisory for this alert.", "run_id": run_id})

    assert response.status_code == 200
    assert response.json()["intent"] == "ACTION_COMMAND"
    assert response.json()["response"]["action"]["status"] == "pending_approval"
    assert response.json()["response"]["approval"]["status"] == "pending_approval"


def test_mixed_exposure_and_alert_request_creates_approval_draft() -> None:
    client = TestClient(app)
    analysis = create_selected_analysis(client)

    response = client.post(
        "/api/chat",
        json={
            "message": (
                "What are main roads and assets within this ROI? "
                "Generate an alert for people to avoid this area."
            ),
            "conversation_id": analysis["conversation_id"],
            "run_id": analysis["run"]["run_id"],
            "region_id": "state_nt",
            "region_name": "Northern Territory hotspot cluster focus",
            "aoi": {"center": [-12.4513, 132.9192], "radius_km": 50},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "EXPOSURE_ACTION"
    assert payload["response"]["decomposition"] == ["EXPOSURE_LOOKUP", "ACTION_COMMAND"]
    assert "Critical assets" in payload["response"]["exposure_answer"]
    assert payload["response"]["action"]["status"] == "pending_approval"
    assert payload["response"]["approval"]["status"] == "pending_approval"
    assert "Avoid the affected area" in payload["response"]["action"]["draft"]
    assert len(payload["response"]["tool_trace"]) >= 4


def test_hotspot_visualization_command_returns_downloadable_layers() -> None:
    client = TestClient(app)
    analysis = create_selected_analysis(client)

    response = client.post(
        "/api/chat",
        json={
            "message": "Create a hotspot heatmap and contour visualization for this AOI.",
            "conversation_id": analysis["conversation_id"],
            "run_id": analysis["run"]["run_id"],
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
    assert any(
        abs(cell["lat"] + 12.4513) < 0.25 and abs(cell["lon"] - 132.9192) < 0.25
        for cell in visualization["heatmap"]["cells"]
    )
    assert len(visualization["contours"]["features"]) == 3
    priority_contour = visualization["contours"]["features"][0]["geometry"]["coordinates"][0]
    assert any(abs(lat + 12.4513) < 1.0 and abs(lon - 132.9192) < 1.0 for lon, lat in priority_contour)
    assert visualization["preview"]["format"] == "image/png"
    assert visualization["preview"]["data_url"].startswith("data:image/png;base64,")
    assert visualization["preview"]["width"] > 0
    assert visualization["downloads"]["txt_filename"].endswith(".txt")
    assert visualization["downloads"]["png_filename"].endswith(".png")
    assert "Satellite hotspots indicate thermal anomalies" in visualization["interpretation"]["caveat"]


def test_monitor_task_command_creates_active_task() -> None:
    client = TestClient(app)
    analysis = create_selected_analysis(client)

    response = client.post(
        "/api/chat",
        json={
            "message": "Create a monitor task for this state every 90 minutes.",
            "conversation_id": analysis["conversation_id"],
            "run_id": analysis["run"]["run_id"],
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
    assert task["interval_minutes"] == 90
    assert task["region_name"] == "Northern Territory hotspot cluster focus"
    assert "every 90 minutes" in payload["response"]["answer"]

    tasks_response = client.get("/api/monitor-tasks")
    assert tasks_response.status_code == 200
    assert tasks_response.json()["monitor_tasks"][0]["task_id"] == task["task_id"]


def test_follow_up_uses_conversation_history_after_analysis() -> None:
    client = TestClient(app)
    analysis = create_selected_analysis(client)

    response = client.post(
        "/api/chat",
        json={
            "message": "Which area should we inspect first?",
            "conversation_id": analysis["conversation_id"],
            "region_id": "state_nt",
            "region_name": "Northern Territory hotspot cluster focus",
            "aoi": {"center": [-12.4513, 132.9192], "radius_km": 50},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["conversation_id"] == analysis["conversation_id"]
    assert payload["response"]["status"] == "success"
    assert len(payload["messages"]) >= 4
    assert "Latest analysis" in payload["context_summary"]


def test_conversation_context_compresses_to_recent_messages() -> None:
    client = TestClient(app)
    analysis = create_selected_analysis(client)

    conversation_id = analysis["conversation_id"]
    for index in range(4):
        response = client.post(
            "/api/chat",
            json={
                "message": f"Question {index}: why is this risk high?",
                "conversation_id": conversation_id,
                "region_id": "state_nt",
            },
        )
        assert response.status_code == 200

    payload = response.json()
    assert len(payload["messages"]) == 6
    assert "Earlier intents" in payload["context_summary"]


def test_action_command_does_not_execute_external_action_directly() -> None:
    client = TestClient(app)
    run_id = create_run(client)

    response = client.post("/api/chat", json={"message": "Draft an email to emergency services.", "run_id": run_id})

    assert response.status_code == 200
    assert response.json()["response"]["action"]["status"] == "pending_approval"
    assert "requires human approval" in response.json()["response"]["safety_note"]
