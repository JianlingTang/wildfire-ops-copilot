from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from app.agents.specialists.analyst_agent import answer_operational_question
from app.agents.specialists.report_agent import create_report_for_run
from app.agents.specialists.what_if_agent import run_what_if
from app.agents.workflows.action_workflow import draft_action
from app.models.schemas import Aoi, ChatRequest
from app.runtime.analysis import execute_analysis_request
from app.services.firestore_store import store


def analyze_and_report_tool(
    user_request: str,
    tool_context: ToolContext,
    region_name: str | None = None,
    region_id: str | None = None,
    aoi_center: list[float] | None = None,
    radius_km: float | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Analysis Workflow: collect AOI evidence, score wildfire risk, create report, and persist run state."""
    request = _chat_request_from_context(
        tool_context,
        user_request,
        region_name=region_name,
        region_id=region_id,
        aoi_center=aoi_center,
        radius_km=radius_km,
        run_id=run_id,
        user_id=user_id,
    )
    artifacts = execute_analysis_request(request, route_label="adk_runtime")
    elastic_evidence = artifacts.run.evidence.get("elastic", {}).get("evidence", [])
    elastic_titles = [
        str(item.get("title"))
        for item in elastic_evidence
        if isinstance(item, dict) and item.get("title")
    ]
    elastic_sentence = (
        f"Elastic MCP retrieved {', '.join(elastic_titles[:2])}."
        if elastic_titles
        else "Elastic MCP evidence was queried."
    )
    payload = {
        "status": "success",
        "mode": "adk",
        "answer": (
            f"{artifacts.run.region_name} is currently {artifacts.run.risk_level} at {artifacts.run.risk_score}/100. "
            f"{artifacts.report.title} was generated and saved. "
            f"{elastic_sentence} "
            + (
                "A high-risk alert was created for operator review."
                if artifacts.alert
                else "No alert was created for this run."
            )
        ),
        "recommendations": artifacts.run.recommendations,
        "evidence_source": f"Elastic MCP {artifacts.run.evidence.get('elastic', {}).get('mode', 'unknown')} evidence",
        "elastic_evidence_titles": elastic_titles,
    }
    payload["tool_trace"] = _analysis_tool_trace(artifacts.run)
    payload["tool_summary"] = payload["tool_trace"][-1]
    _stash_result(
        tool_context,
        intent="ANALYZE_AND_REPORT",
        payload=payload,
        run_id=artifacts.run.run_id,
        report_id=artifacts.report.report_id,
        alert_id=artifacts.alert.alert_id if artifacts.alert else None,
    )
    return {
        "tool_trace": payload["tool_trace"],
        "tool_summary": payload["tool_summary"],
        "region_name": artifacts.run.region_name,
        "risk_level": artifacts.run.risk_level,
        "risk_score": artifacts.run.risk_score,
        "report_title": artifacts.report.title,
        "alert_created": bool(artifacts.alert),
        "top_recommendation": artifacts.run.recommendations[0] if artifacts.run.recommendations else None,
        "evidence_source": payload["evidence_source"],
        "elastic_evidence_titles": elastic_titles,
    }


def what_if_tool(
    user_request: str,
    tool_context: ToolContext,
    region_name: str | None = None,
    region_id: str | None = None,
    aoi_center: list[float] | None = None,
    radius_km: float | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """What-if Workflow: parse scenario changes and compare baseline risk with scenario risk."""
    run = _resolve_run(tool_context)
    request = _chat_request_from_context(
        tool_context,
        user_request,
        region_name=region_name,
        region_id=region_id,
        aoi_center=aoi_center,
        radius_km=radius_km,
        run_id=run_id,
        user_id=user_id,
    )
    payload = run_what_if(user_request, run, request.region_name, request.aoi)
    payload["mode"] = "adk"
    payload["tool_trace"] = _what_if_tool_trace(payload, request.region_name or request.region_id)
    payload["tool_summary"] = payload["tool_trace"][-1]
    _stash_result(
        tool_context,
        intent="WHAT_IF",
        payload=payload,
        run_id=run.run_id if run else None,
    )
    return payload


def action_command_tool(
    user_request: str,
    tool_context: ToolContext,
    region_name: str | None = None,
    region_id: str | None = None,
    aoi_center: list[float] | None = None,
    radius_km: float | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Action Workflow: draft operator action text and create a pending human approval record."""
    run = _resolve_run(tool_context)
    request = _chat_request_from_context(
        tool_context,
        user_request,
        region_name=region_name,
        region_id=region_id,
        aoi_center=aoi_center,
        radius_km=radius_km,
        run_id=run_id,
        user_id=user_id,
    )
    requested_by = request.user_id or str(tool_context.state.get("app:user_id", "demo_officer"))
    payload = draft_action(user_request, run, requested_by, request.region_name)
    payload["mode"] = "adk"
    action = payload.get("action") or {}
    payload["tool_trace"] = _action_tool_trace(payload)
    payload["tool_summary"] = payload["tool_trace"][-1]
    _stash_result(
        tool_context,
        intent="ACTION_COMMAND",
        payload=payload,
        run_id=run.run_id if run else None,
        action_id=action.get("action_id"),
    )
    return payload


def report_request_tool(
    user_request: str,
    tool_context: ToolContext,
    region_name: str | None = None,
    region_id: str | None = None,
    aoi_center: list[float] | None = None,
    radius_km: float | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Report Workflow: generate and save a report from the latest completed analysis run."""
    del user_request, region_name, region_id, aoi_center, radius_km, run_id, user_id
    run = _resolve_run(tool_context)
    payload = create_report_for_run(run)
    payload["mode"] = "adk"
    report = payload.get("report") or {}
    payload["tool_trace"] = _report_tool_trace(payload)
    payload["tool_summary"] = payload["tool_trace"][-1]
    _stash_result(
        tool_context,
        intent="REPORT_REQUEST",
        payload=payload,
        run_id=run.run_id if run else None,
        report_id=report.get("report_id"),
    )
    return payload


def analyst_question_tool(
    user_request: str,
    tool_context: ToolContext,
    region_name: str | None = None,
    region_id: str | None = None,
    aoi_center: list[float] | None = None,
    radius_km: float | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Analyst Workflow: answer operational questions from latest run or selected Focus AOI context."""
    run = _resolve_run(tool_context)
    request = _chat_request_from_context(
        tool_context,
        user_request,
        region_name=region_name,
        region_id=region_id,
        aoi_center=aoi_center,
        radius_km=radius_km,
        run_id=run_id,
        user_id=user_id,
    )
    payload = answer_operational_question(user_request, run, request.region_name, request.aoi)
    payload["mode"] = "adk"
    payload["tool_trace"] = _analyst_tool_trace(payload, request.region_name or request.region_id)
    payload["tool_summary"] = payload["tool_trace"][-1]
    _stash_result(
        tool_context,
        intent="ANALYST_QA",
        payload=payload,
        run_id=run.run_id if run else None,
    )
    return payload


def _chat_request_from_context(
    tool_context: ToolContext,
    message: str,
    *,
    region_name: str | None = None,
    region_id: str | None = None,
    aoi_center: list[float] | None = None,
    radius_km: float | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
) -> ChatRequest:
    center = aoi_center or tool_context.state.get("app:aoi_center")
    effective_radius_km = radius_km or tool_context.state.get("app:aoi_radius_km")
    aoi = None
    if isinstance(center, (list, tuple)) and len(center) == 2 and effective_radius_km:
        aoi = Aoi(center=(float(center[0]), float(center[1])), radius_km=float(effective_radius_km))
    return ChatRequest(
        message=message,
        run_id=_normalize_optional_str(run_id or tool_context.state.get("app:run_id")),
        region_id=str(region_id or tool_context.state.get("app:region_id", "live_australia")),
        region_name=_normalize_optional_str(region_name or tool_context.state.get("app:region_name")),
        aoi=aoi,
        user_id=str(user_id or tool_context.state.get("app:user_id", "demo_officer")),
    )


def _resolve_run(tool_context: ToolContext):
    run_id = _normalize_optional_str(tool_context.state.get("app:run_id"))
    if run_id and run_id in store.runs:
        return store.runs[run_id]
    region_id = _normalize_optional_str(tool_context.state.get("app:region_id"))
    return store.get_latest_run(region_id)


def _stash_result(
    tool_context: ToolContext,
    *,
    intent: str,
    payload: dict[str, Any],
    run_id: str | None = None,
    report_id: str | None = None,
    alert_id: str | None = None,
    action_id: str | None = None,
) -> None:
    tool_context.state["last_intent"] = intent
    tool_context.state["last_response_payload"] = payload
    if run_id:
        tool_context.state["last_run_id"] = run_id
        tool_context.state["app:run_id"] = run_id
    if report_id:
        tool_context.state["last_report_id"] = report_id
    if alert_id:
        tool_context.state["last_alert_id"] = alert_id
    if action_id:
        tool_context.state["last_action_id"] = action_id


def _normalize_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _analysis_tool_trace(run) -> list[dict[str, Any]]:
    hotspots = run.evidence.get("hotspots", {})
    warnings = run.evidence.get("official_warnings", {})
    elastic = run.evidence.get("elastic", {})
    elastic_items = elastic.get("evidence", [])
    elastic_title = elastic_items[0].get("title") if elastic_items else "No Elastic evidence title"
    return [
        _trace_item("Main Coordinator", "Selected Analysis Workflow.", run.region_name),
        _trace_item(
            "External Data Tools",
            "Called hotspot, weather, warning, and exposure tools.",
            f"{hotspots.get('data', {}).get('count_24h', '--')} hotspots, "
            f"{warnings.get('data', {}).get('incident_count', 0)} warnings.",
        ),
        _trace_item(
            "Elastic MCP Tool",
            "Queried operational evidence.",
            f"{elastic_title} ({elastic.get('mode', 'unknown')} mode).",
            status="failed" if elastic.get("mode") == "fallback" else "completed",
        ),
        _trace_item(
            "Risk + Report Agents",
            "Computed risk score and generated report.",
            f"{run.risk_level} {run.risk_score}/100.",
        ),
    ]


def _what_if_tool_trace(payload: dict[str, Any], region_name: str) -> list[dict[str, Any]]:
    baseline = payload.get("baseline", {})
    scenario = payload.get("scenario", {})
    return [
        _trace_item("Main Coordinator", "Selected What-if Agent.", region_name),
        _trace_item(
            "Scenario Parser",
            "Parsed scenario request.",
            str(payload.get("scenario_delta") or scenario.get("delta") or {}),
        ),
        _trace_item(
            "Risk Engine",
            "Computed baseline and scenario.",
            f"{baseline.get('risk_level', 'baseline pending')} -> "
            f"{scenario.get('risk_level', scenario.get('qualitative_risk', 'scenario pending'))}.",
        ),
    ]


def _action_tool_trace(payload: dict[str, Any]) -> list[dict[str, Any]]:
    action = payload.get("action", {})
    approval = payload.get("approval", {})
    return [
        _trace_item("Main Coordinator", "Selected Action Workflow.", action.get("action_type", "action command")),
        _trace_item(
            "Approval Workflow",
            "Created draft action and approval record.",
            action.get("title", "Draft created."),
        ),
        _trace_item(
            "Safety Boundary",
            "Blocked direct external execution.",
            approval.get("status", "Human approval required."),
        ),
    ]


def _report_tool_trace(payload: dict[str, Any]) -> list[dict[str, Any]]:
    report = payload.get("report", {})
    return [
        _trace_item("Main Coordinator", "Selected Report Agent.", "Report request."),
        _trace_item(
            "Report Agent",
            "Generated report from latest run.",
            report.get("title", payload.get("message", "Report pending.")),
        ),
    ]


def _analyst_tool_trace(payload: dict[str, Any], region_name: str) -> list[dict[str, Any]]:
    return [
        _trace_item("Main Coordinator", "Selected Analyst Agent.", region_name),
        _trace_item(
            "Analyst Agent",
            "Answered from active run or Focus AOI context.",
            payload.get("status", "success"),
        ),
    ]


def _trace_item(
    called: str,
    did: str,
    output: Any,
    *,
    mode: str = "adk",
    status: str = "completed",
    next_step: str | None = None,
) -> dict[str, Any]:
    item = {
        "called": called,
        "did": did,
        "output": str(output),
        "mode": mode,
        "status": status,
    }
    if next_step:
        item["next_step"] = next_step
    return item
