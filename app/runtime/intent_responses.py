from __future__ import annotations

from typing import Any

from app.models.schemas import ChatRequest, RunRecord
from app.services.agent_events import publish_agent_event

# Single source of truth for the tool_trace/response shapes needed by all three chat
# runtimes: the ADK LLM tool surface (wildfire_ops_agent/tools.py), the ADK runtime's
# deterministic fallback (app/runtime/adk.py), and the LLM-free demo runtime
# (app/runtime/mock_demo.py). Each intent needs an identical trace regardless of which
# of the three called it; keeping one copy prevents the three from drifting apart.


def trace_item(
    called: str,
    did: str,
    output: Any,
    *,
    mode: str = "adk",
    status: str = "completed",
    next_step: str | None = None,
) -> dict[str, Any]:
    item = {"called": called, "did": did, "output": str(output), "mode": mode, "status": status}
    if next_step:
        item["next_step"] = next_step
    return item


def knowledge_required_response(message: str, *, mode: str = "adk") -> dict[str, Any]:
    return {
        "status": "knowledge_required",
        "mode": mode,
        "answer": (
            "This wildfire question requires verified document retrieval, but the production RAG pipeline is not "
            "enabled in this phase. I will not answer from model memory."
        ),
        "requires_rag": True,
        "query": message,
        "tool_trace": [
            trace_item(
                "Knowledge Retrieval Required",
                "Stopped before generation because no deterministic tool can answer the request.",
                "Verified document retrieval is required.",
                mode=mode,
                status="blocked",
            )
        ],
    }


def analysis_trace(run: RunRecord, *, mode: str = "adk") -> list[dict[str, Any]]:
    hotspots = run.evidence.get("hotspots", {})
    warnings = run.evidence.get("official_warnings", {})
    elastic = run.evidence.get("elastic", {})
    elastic_items = elastic.get("evidence", [])
    elastic_title = elastic_items[0].get("title") if elastic_items else "No Elastic evidence title"
    return [
        trace_item("Main Coordinator", "Selected Analysis Workflow.", run.region_name, mode=mode),
        trace_item(
            "External Data Tools",
            "Called hotspot, weather, warning, and exposure tools.",
            f"{hotspots.get('data', {}).get('count_24h', '--')} hotspots, "
            f"{warnings.get('data', {}).get('incident_count', 0)} warnings.",
            mode=mode,
        ),
        trace_item(
            "Elastic MCP Tool",
            "Queried operational evidence.",
            f"{elastic_title} ({elastic.get('mode', 'unknown')} mode).",
            mode=mode,
            status="failed" if elastic.get("mode") == "fallback" else "completed",
        ),
        trace_item(
            "Risk + Report Agents",
            "Computed risk score and generated report.",
            f"{run.risk_level} {run.risk_score}/100.",
            mode=mode,
        ),
    ]


def trace_for_intent(
    intent: str,
    payload: dict[str, Any],
    *,
    region_name: str | None,
    mode: str = "adk",
) -> list[dict[str, Any]]:
    if intent == "WHAT_IF":
        scenario = payload.get("scenario", {})
        baseline = payload.get("baseline", {})
        scenario_delta = payload.get("scenario_delta") or scenario.get("delta") or {}
        scenario_level = scenario.get("risk_level", scenario.get("qualitative_risk", "scenario pending"))
        return [
            trace_item("Main Coordinator", "Selected What-if Agent.", region_name, mode=mode),
            trace_item("Scenario Parser", "Parsed scenario request.", str(scenario_delta), mode=mode),
            trace_item(
                "Risk Engine",
                "Computed baseline and scenario.",
                f"{baseline.get('risk_level', 'baseline pending')} -> {scenario_level}.",
                mode=mode,
            ),
        ]
    if intent == "ACTION_COMMAND":
        action = payload.get("action", {})
        approval = payload.get("approval", {})
        return [
            trace_item(
                "Main Coordinator",
                "Selected Action Workflow.",
                action.get("action_type", "action command"),
                mode=mode,
            ),
            trace_item(
                "Approval Workflow",
                "Created draft action and approval record.",
                action.get("title", "Draft created."),
                mode=mode,
            ),
            trace_item(
                "Safety Boundary",
                "Blocked direct external execution.",
                approval.get("status", "Human approval required."),
                mode=mode,
            ),
        ]
    if intent == "HOTSPOT_VISUALIZATION":
        visualization = payload.get("visualization", {})
        return [
            trace_item(
                "Main Coordinator",
                "Selected Hotspot Visualization Workflow.",
                visualization.get("region", {}).get("region_name", region_name),
                mode=mode,
            ),
            trace_item(
                "Hotspot Density Tool",
                "Computed heatmap cells.",
                f"{len(visualization.get('heatmap', {}).get('cells', []))} cells",
                mode=mode,
            ),
            trace_item(
                "Contour Tool",
                "Generated contour GeoJSON.",
                f"{len(visualization.get('contours', {}).get('features', []))} contour bands",
                mode=mode,
            ),
            trace_item(
                "AI Map Interpreter",
                "Summarized hotspot pattern.",
                visualization.get("interpretation", {}).get("priority"),
                mode=mode,
            ),
        ]
    if intent == "REPORT_REQUEST":
        report = payload.get("report", {})
        return [
            trace_item("Main Coordinator", "Selected Report Agent.", "Report request.", mode=mode),
            trace_item(
                "Report Agent",
                "Generated report from latest run.",
                report.get("title", payload.get("message", "Report pending.")),
                mode=mode,
            ),
        ]
    # ANALYST_QA and the operational-question fallback intents (CHANGE_EXPLANATION, WEATHER_CHANGE,
    # WIND_CHANGE, RISK_EXPLANATION, OPERATIONAL_PRIORITIZATION, EXPOSURE_LOOKUP, QUESTION) share one trace.
    return [
        trace_item("Main Coordinator", "Selected Analyst Agent.", region_name, mode=mode),
        trace_item(
            "Analyst Agent",
            "Answered from active run or Focus AOI context.",
            payload.get("status", "success"),
            mode=mode,
        ),
    ]


def publish_chat_event(
    trace_id: str,
    request: ChatRequest,
    conversation_id: str,
    status: str,
    message: str,
    intent: str,
    *,
    mode: str,
) -> None:
    publish_agent_event(
        trace_id=trace_id,
        conversation_id=conversation_id,
        run_id=request.run_id,
        region_id=request.region_id,
        agent_type="coordinator",
        status=status,
        message=message,
        data={"intent": intent, "mode": mode},
    )


def publish_artifact_event(
    trace_id: str,
    request: ChatRequest,
    conversation_id: str,
    agent_type: str,
    message: str,
    intent: str,
    *,
    mode: str,
) -> None:
    publish_agent_event(
        trace_id=trace_id,
        conversation_id=conversation_id,
        run_id=request.run_id,
        region_id=request.region_id,
        agent_type=agent_type,
        status="completed",
        message=message,
        data={"intent": intent, "mode": mode},
    )
