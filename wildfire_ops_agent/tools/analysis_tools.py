"""ADK tools for the analysis/report/calculation/analyst-question family."""

from __future__ import annotations

from typing import Any

from google.adk.tools import ToolContext

from app.agents.specialists.analyst_agent import answer_operational_question
from app.agents.specialists.report_agent import create_report_for_run
from app.runtime.analysis import execute_analysis_request
from app.runtime.intent_responses import analysis_trace, knowledge_required_response, trace_for_intent, trace_item
from app.services.deterministic_calculator import CalculationOperation, calculate
from app.services.risk_trend import build_risk_prediction_response, build_risk_trend_response
from wildfire_ops_agent.tools._shared import _chat_request_from_context, _resolve_run, _stash_result


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
    elastic_titles = _elastic_evidence_titles(artifacts.run)
    payload = _analyze_and_report_payload(artifacts, elastic_titles)
    payload["tool_trace"] = analysis_trace(artifacts.run)
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


def _elastic_evidence_titles(run: Any) -> list[str]:
    elastic_evidence = run.evidence.get("elastic", {}).get("evidence", [])
    return [str(item.get("title")) for item in elastic_evidence if isinstance(item, dict) and item.get("title")]


def _analyze_and_report_payload(artifacts: Any, elastic_titles: list[str]) -> dict[str, Any]:
    elastic_sentence = (
        f"Elastic MCP retrieved {', '.join(elastic_titles[:2])}."
        if elastic_titles
        else "Elastic MCP evidence was queried."
    )
    alert_sentence = (
        "A high-risk alert was created for operator review."
        if artifacts.alert
        else "No alert was created for this run."
    )
    return {
        "status": "success",
        "mode": "adk",
        "answer": (
            f"{artifacts.run.region_name} is currently {artifacts.run.risk_level} at {artifacts.run.risk_score}/100. "
            f"{artifacts.report.title} was generated and saved. "
            f"{elastic_sentence} {alert_sentence}"
        ),
        "recommendations": artifacts.run.recommendations,
        "evidence_source": f"Elastic MCP {artifacts.run.evidence.get('elastic', {}).get('mode', 'unknown')} evidence",
        "elastic_evidence_titles": elastic_titles,
    }


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
    payload["tool_trace"] = trace_for_intent("REPORT_REQUEST", payload, region_name=None)
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
    payload["tool_trace"] = trace_for_intent(
        "ANALYST_QA", payload, region_name=request.region_name or request.region_id
    )
    payload["tool_summary"] = payload["tool_trace"][-1]
    _stash_result(tool_context, intent="ANALYST_QA", payload=payload, run_id=run.run_id if run else None)
    return payload


def deterministic_calculation_tool(
    user_request: str,
    operation: CalculationOperation,
    values: list[float],
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Deterministic Calculator: execute an audited arithmetic or AOI-area calculation in Python."""
    try:
        payload = _successful_calculation_payload(operation, values)
    except ValueError as exc:
        payload = _invalid_calculation_payload(operation, values, exc)
    payload["user_request"] = user_request
    payload["tool_summary"] = payload["tool_trace"][-1]
    _stash_result(tool_context, intent="CALCULATION", payload=payload)
    return payload


def _successful_calculation_payload(operation: CalculationOperation, values: list[float]) -> dict[str, Any]:
    result = calculate(operation, values)
    return {
        "status": "success",
        "mode": "adk",
        "answer": f"Deterministic calculation result: {result:.6g}.",
        "calculation": {"operation": operation, "values": values, "result": result, "implementation": "python"},
        "tool_trace": [
            trace_item("Deterministic Python Calculator", f"Executed {operation} without model arithmetic.", result)
        ],
    }


def _invalid_calculation_payload(
    operation: CalculationOperation, values: list[float], exc: ValueError
) -> dict[str, Any]:
    return {
        "status": "invalid_input",
        "mode": "adk",
        "answer": f"The deterministic calculation could not run: {exc}.",
        "calculation": {"operation": operation, "values": values},
        "tool_trace": [
            trace_item("Deterministic Python Calculator", f"Rejected invalid {operation} inputs.", exc, status="failed")
        ],
    }


def risk_trend_tool(
    user_request: str,
    tool_context: ToolContext,
    region_name: str | None = None,
    region_id: str | None = None,
    aoi_center: list[float] | None = None,
    radius_km: float | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Risk Trend Tool: build the deterministic analysis risk timeseries and chart."""
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
    run = _resolve_run(tool_context)
    payload = build_risk_trend_response(request, run, mode="adk")
    payload["tool_summary"] = payload["tool_trace"][-1]
    _stash_result(tool_context, intent="RISK_TREND", payload=payload, run_id=run.run_id if run else None)
    return payload


def risk_prediction_tool(
    user_request: str,
    tool_context: ToolContext,
    region_name: str | None = None,
    region_id: str | None = None,
    aoi_center: list[float] | None = None,
    radius_km: float | None = None,
    run_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Risk Prediction Tool: build the deterministic +5 day risk forecast artifact."""
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
    run = _resolve_run(tool_context)
    payload = build_risk_prediction_response(request, run, mode="adk")
    payload["tool_summary"] = payload["tool_trace"][-1]
    _stash_result(tool_context, intent="RISK_PREDICTION", payload=payload, run_id=run.run_id if run else None)
    return payload


def knowledge_retrieval_required_tool(user_request: str, tool_context: ToolContext) -> dict[str, Any]:
    """RAG Handoff: refuse unsupported knowledge answers until evidence retrieval is implemented."""
    payload: dict[str, Any] = knowledge_required_response(user_request)
    payload["tool_summary"] = payload["tool_trace"][-1]
    _stash_result(tool_context, intent="KNOWLEDGE_REQUIRED", payload=payload)
    return payload
