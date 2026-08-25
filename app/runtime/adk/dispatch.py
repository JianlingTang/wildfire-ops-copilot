"""Deterministic (non-LLM) per-intent workflow dispatch for the ADK runtime.

Used both as the fallback when the LlmAgent doesn't call a required tool
(app.runtime.adk.__init__) and as the ANALYZE_AND_REPORT/HOTSPOT_VISUALIZATION
handler for the deterministic path itself.
"""

from __future__ import annotations

from typing import Any

from app.agents.specialists.analyst_agent import answer_operational_question
from app.agents.specialists.report_agent import create_report_for_run
from app.agents.specialists.what_if_agent import run_what_if
from app.agents.workflows.action_workflow import draft_action
from app.config.settings import settings
from app.models.schemas import ChatRequest, RunRecord
from app.runtime.adk.response import _apply_synthesis_answer, _error_response
from app.runtime.analysis import execute_analysis_request
from app.runtime.intent_responses import (
    analysis_trace,
    knowledge_required_response,
    trace_for_intent,
    trace_item,
)
from app.services.conversation_memory import lookup_conversation_memory, memory_operation_for_message
from app.services.deterministic_calculator import calculation_response_from_message
from app.services.firestore_store import store
from app.services.hotspot_visualization import build_hotspot_visualization
from app.services.monitoring_tasks import create_monitor_task_from_chat

ANALYST_SYNTHESIS_INTENTS = {
    "CHANGE_EXPLANATION",
    "WEATHER_CHANGE",
    "WIND_CHANGE",
    "RISK_EXPLANATION",
    "OPERATIONAL_PRIORITIZATION",
    "EXPOSURE_LOOKUP",
    "QUESTION",
}


def _route_deterministic_workflow(
    request: ChatRequest,
    intent: str,
    correction_summary: str | None = None,
) -> dict[str, Any] | None:
    run = _resolve_run_for_request(request)
    if intent == "MEMORY_LOOKUP":
        return _memory_lookup_workflow(request, correction_summary)
    if intent == "CALCULATION":
        return _calculation_workflow(request, correction_summary)
    if intent == "KNOWLEDGE_REQUIRED":
        return _knowledge_required_workflow(request, correction_summary)
    if intent == "ANALYZE_AND_REPORT":
        return _analyze_and_report_workflow(request, correction_summary)
    if intent == "HOTSPOT_VISUALIZATION":
        return _hotspot_visualization_workflow(request, correction_summary)
    if intent == "MONITOR_TASK":
        return _monitor_task_workflow(request, correction_summary)
    if intent == "WHAT_IF":
        return _what_if_workflow(request, run, correction_summary)
    if intent == "ACTION_COMMAND":
        return _action_command_workflow(request, run, correction_summary)
    if intent == "REPORT_REQUEST":
        return _report_request_workflow(request, run, correction_summary)
    if intent in ANALYST_SYNTHESIS_INTENTS:
        return _route_local_analyst_synthesis(request, intent, correction_summary=correction_summary)
    return _error_response(intent, "Gemini/Vertex AI did not return a usable response.")


def _memory_lookup_workflow(request: ChatRequest, correction_summary: str | None) -> dict[str, Any]:
    operation = memory_operation_for_message(request.message)
    if operation is None:
        return _error_response("MEMORY_LOOKUP", "No supported deterministic memory lookup matched this request.")
    payload = lookup_conversation_memory(request, operation)
    _prepend_correction_trace(payload, correction_summary)
    return {"intent": "MEMORY_LOOKUP", "mode": "adk", "response": payload}


def _calculation_workflow(request: ChatRequest, correction_summary: str | None) -> dict[str, Any]:
    payload = calculation_response_from_message(request.message, mode="adk")
    _prepend_correction_trace(payload, correction_summary)
    return {"intent": "CALCULATION", "mode": "adk", "response": payload}


def _knowledge_required_workflow(request: ChatRequest, correction_summary: str | None) -> dict[str, Any]:
    payload = knowledge_required_response(request.message, mode="adk")
    _prepend_correction_trace(payload, correction_summary)
    return {"intent": "KNOWLEDGE_REQUIRED", "mode": "adk", "response": payload}


def _analyze_and_report_workflow(request: ChatRequest, correction_summary: str | None) -> dict[str, Any]:
    response = _analyze_and_report(request)
    _prepend_correction_trace(response["response"], correction_summary)
    return response


def _hotspot_visualization_workflow(request: ChatRequest, correction_summary: str | None) -> dict[str, Any]:
    payload = _hotspot_visualization_response(request)
    _prepend_correction_trace(payload, correction_summary)
    return {"intent": "HOTSPOT_VISUALIZATION", "mode": "adk", "response": payload}


def _monitor_task_workflow(request: ChatRequest, correction_summary: str | None) -> dict[str, Any]:
    payload = create_monitor_task_from_chat(request)
    _prepend_correction_trace(payload, correction_summary)
    return {"intent": "MONITOR_TASK", "mode": "adk", "response": payload}


def _what_if_workflow(request: ChatRequest, run: RunRecord | None, correction_summary: str | None) -> dict[str, Any]:
    payload = run_what_if(request.message, run, request.region_name, request.aoi)
    _ensure_tool_trace(payload, _trace_for_request("WHAT_IF", payload, request))
    _prepend_correction_trace(payload, correction_summary)
    return {"intent": "WHAT_IF", "mode": "adk", "response": payload}


def _action_command_workflow(
    request: ChatRequest, run: RunRecord | None, correction_summary: str | None
) -> dict[str, Any]:
    payload = draft_action(request.message, run, request.user_id, request.region_name)
    _ensure_tool_trace(payload, _trace_for_request("ACTION_COMMAND", payload, request))
    _prepend_correction_trace(payload, correction_summary)
    return {"intent": "ACTION_COMMAND", "mode": "adk", "response": payload}


def _report_request_workflow(
    request: ChatRequest, run: RunRecord | None, correction_summary: str | None
) -> dict[str, Any]:
    result = create_report_for_run(run)
    _ensure_tool_trace(result, _trace_for_request("REPORT_REQUEST", result, request))
    _prepend_correction_trace(result, correction_summary)
    if result.get("status") == "success":
        result["answer"] = "Generated a fresh operations brief from the latest completed run."
        return {"intent": "REPORT_REQUEST", "mode": "adk", "response": result, "report": result["report"]}
    return {"intent": "REPORT_REQUEST", "mode": "adk", "response": result}


def _route_local_analyst_synthesis(
    request: ChatRequest,
    intent: str,
    correction_summary: str | None = None,
) -> dict[str, Any] | None:
    if intent not in ANALYST_SYNTHESIS_INTENTS:
        return None
    run = _resolve_run_for_request(request)
    payload = answer_operational_question(request.message, run, request.region_name, request.aoi)
    payload["mode"] = "adk"
    _ensure_tool_trace(payload, _trace_for_request(intent, payload, request))
    _prepend_correction_trace(payload, correction_summary)
    if payload.get("requires_synthesis"):
        _apply_synthesis_answer(payload, None, request)
    response: dict[str, Any] = {"intent": intent, "mode": "adk", "response": payload}
    if run:
        response["run"] = run
    return response


def _trace_for_request(intent: str, payload: dict[str, Any], request: ChatRequest) -> list[dict[str, Any]]:
    return trace_for_intent(intent, payload, region_name=request.region_name or request.region_id, mode="adk")


def _resolve_run_for_request(request: ChatRequest) -> RunRecord | None:
    run = store.runs.get(request.run_id) if request.run_id else store.get_latest_run(request.region_id)
    if run is None and request.region_id == settings.demo_region_id:
        run = store.get_latest_run()
    return run


def _ensure_tool_trace(payload: dict[str, Any], trace: list[dict[str, Any]]) -> None:
    payload.setdefault("tool_trace", trace)


def _prepend_correction_trace(payload: dict[str, Any], correction_summary: str | None) -> None:
    if not correction_summary:
        return
    trace = payload.setdefault("tool_trace", [])
    trace.insert(
        0,
        trace_item(
            "Main Coordinator",
            "Applied deterministic guardrail.",
            correction_summary,
            status="completed",
        ),
    )


def _hotspot_visualization_response(request: ChatRequest) -> dict[str, Any]:
    visualization = build_hotspot_visualization(request)
    payload = {
        "status": "success",
        "mode": "adk",
        "answer": (
            f"Generated hotspot heatmap and contour analysis for {visualization['region']['region_name']}. "
            f"{visualization['interpretation']['summary']} The visualization is ready to download."
        ),
        "visualization": visualization,
    }
    _ensure_tool_trace(payload, _trace_for_request("HOTSPOT_VISUALIZATION", payload, request))
    return payload


def _analyze_and_report(request: ChatRequest) -> dict[str, Any]:
    artifacts = execute_analysis_request(request, route_label="adk_runtime")
    answer = _operator_summary(
        artifacts.run,
        artifacts.report.model_dump(),
        artifacts.alert.model_dump() if artifacts.alert else None,
    )
    store.add_event(
        artifacts.run.run_id,
        "adk_runtime",
        "return_operator_summary",
        "completed",
        "Returned the operator summary and dashboard payload.",
    )
    return {
        "intent": "ANALYZE_AND_REPORT",
        "mode": "adk",
        "response": {
            "status": "success",
            "mode": "adk",
            "answer": answer,
            "recommendations": artifacts.run.recommendations,
            "evidence_source": _elastic_evidence_source(artifacts.run),
            "tool_trace": analysis_trace(artifacts.run, mode="adk"),
        },
        "run": artifacts.run,
        "report": artifacts.report,
        "alert": artifacts.alert,
    }


def _operator_summary(run_record: RunRecord, report: dict, alert: dict | None) -> str:
    evidence_parts = _evidence_parts(run_record)
    evidence_sentence = _elastic_evidence_sentence(run_record)
    alert_sentence = (
        "A high-risk alert was created for operator review." if alert else "No alert was created for this run."
    )
    analysis_sentence = (
        f"after a chat-driven analysis using {', '.join(evidence_parts)}. "
        if evidence_parts
        else "after a chat-driven analysis. "
    )
    return (
        f"{run_record.region_name} is currently {run_record.risk_level} at {run_record.risk_score}/100 "
        f"{analysis_sentence}"
        f"{evidence_sentence} "
        f"The top recommendation is to {run_record.recommendations[0].lower()} "
        f"{report['title']} was generated and saved to the dashboard. {alert_sentence}"
    )


def _evidence_parts(run_record: RunRecord) -> list[str]:
    hotspots = run_record.evidence.get("hotspots", {})
    hotspot_count = hotspots.get("data", {}).get("count_24h")
    weather_data = run_record.evidence.get("weather", {}).get("data", {})
    warnings = run_record.evidence.get("official_warnings", {})
    warning_count = warnings.get("data", {}).get("incident_count")
    parts = []
    if hotspot_count is not None:
        parts.append(f"the hotspot tool found {hotspot_count} detections in the last 24 hours")
    if weather_data:
        parts.append(
            "the weather tool shows "
            f"{weather_data.get('wind_gust_max', 'unknown')} km/h gusts, "
            f"{weather_data.get('humidity_min', 'unknown')}% minimum humidity, and "
            f"{weather_data.get('rainfall_7d', 'unknown')} mm seven-day rainfall"
        )
    if warning_count is not None:
        parts.append(f"the warnings tool found {warning_count} nearby official warnings")
    return parts


def _elastic_evidence_sentence(run_record: RunRecord) -> str:
    elastic = run_record.evidence.get("elastic", {})
    elastic_mode = elastic.get("mode", "unknown")
    elastic_items = elastic.get("evidence", [])
    if elastic_items:
        titles = ", ".join(str(item.get("title", "Elastic MCP evidence")) for item in elastic_items[:2])
        return f"Elastic MCP evidence ({elastic_mode} mode) retrieved {titles}."
    return f"Elastic MCP evidence ran in {elastic_mode} mode."


def _elastic_evidence_source(run_record: RunRecord) -> str:
    elastic = run_record.evidence.get("elastic", {})
    source = elastic.get("source") or "Elastic MCP"
    mode = elastic.get("mode", "unknown")
    return f"{source} ({mode} mode)"
