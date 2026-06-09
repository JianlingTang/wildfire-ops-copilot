from __future__ import annotations

import asyncio
import os
from typing import Any

import google.auth
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.auth.exceptions import DefaultCredentialsError
from google.genai import types

from app.agents.specialists.analyst_agent import answer_operational_question
from app.agents.specialists.report_agent import create_report_for_run
from app.agents.specialists.what_if_agent import run_what_if
from app.agents.workflows.action_workflow import draft_action
from app.agents.workflows.daily_intelligence import run_daily_intelligence
from app.config.settings import settings
from app.models.schemas import ChatRequest, ManualRunRequest, RunRecord
from app.runtime.analysis import execute_analysis_request
from app.runtime.base import AgentRuntime
from app.runtime.intents import classify_intent
from app.services.firestore_store import store
from wildfire_ops_agent.agent import root_agent

APP_NAME = os.getenv("ADK_APP_NAME", "wildfire_ops_agent")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
_SESSION_SERVICE: InMemorySessionService | None = None
_RUNNER: Runner | None = None


class AdkRuntime(AgentRuntime):
    """Google ADK + Gemini runtime behind the existing FastAPI contract."""

    def run_daily(self) -> dict:
        request = ManualRunRequest(region_id=settings.demo_region_id, region_name=settings.demo_region_name)
        return run_daily_intelligence(request, trigger_type="daily")

    def run_manual(self, request: ManualRunRequest) -> dict:
        return run_daily_intelligence(request, trigger_type="manual")

    def route_chat(self, request: ChatRequest) -> dict:
        return asyncio.run(self._route_chat_async(request))

    async def _route_chat_async(self, request: ChatRequest) -> dict:
        intent = classify_intent(request.message)
        try:
            _ensure_vertex_configuration()
            session_service = _get_session_service()
            runner = _get_runner()
            user_id = request.user_id or "demo_officer"
            session_id = _session_id_for(request)
            await _ensure_session(session_service, user_id, session_id)
            await _merge_request_state(session_service, user_id, session_id, request)

            final_text: str | None = None
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text=_message_with_operational_context(request))],
                ),
                state_delta=_state_delta_for_request(request),
            ):
                if event.is_final_response():
                    text = _extract_text(event.content)
                    if text:
                        final_text = text

            session = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
            session_state = session.state if session else {}
            runtime_intent = str(session_state.get("last_intent") or "")
            if not runtime_intent:
                fallback = _route_deterministic_workflow(
                    request,
                    intent,
                    correction_summary="Deterministic fallback ran because the LLM did not call a workflow tool.",
                )
                if fallback is not None:
                    return fallback
            elif _should_correct_llm_route(intent, runtime_intent):
                corrected = _route_deterministic_workflow(
                    request,
                    intent,
                    correction_summary=(
                        f"Deterministic guardrail corrected route from "
                        f"{runtime_intent or 'no tool call'} to {intent}."
                    ),
                )
                if corrected is not None:
                    return corrected

            response = _build_runtime_response(request, session_state, final_text)
            if _missing_tool_result(response):
                fallback = _route_deterministic_workflow(
                    request,
                    intent,
                    correction_summary="Deterministic fallback ran because the LLM did not call a workflow tool.",
                )
                if fallback is not None:
                    return fallback
            if _needs_focus_aoi_fallback(response, request, intent):
                fallback = _route_deterministic_workflow(
                    request,
                    intent,
                    correction_summary=(
                        "Deterministic guardrail answered from Focus AOI context because "
                        "the LLM tool result did not use the selected AOI."
                    ),
                )
                if fallback is not None:
                    return fallback
            return response
        except Exception as exc:
            fallback = _route_deterministic_workflow(
                request,
                intent,
                correction_summary=f"Deterministic fallback ran because ADK runtime failed: {exc}",
            )
            if fallback is not None:
                return fallback
            return _error_response(intent, f"ADK runtime failed: {exc}")


def _route_deterministic_workflow(
    request: ChatRequest,
    intent: str,
    correction_summary: str | None = None,
) -> dict[str, Any] | None:
    run = _resolve_run_for_request(request)
    if intent == "ANALYZE_AND_REPORT":
        response = _analyze_and_report(request)
        _prepend_correction_trace(response["response"], correction_summary)
        return response
    if intent == "WHAT_IF":
        payload = run_what_if(request.message, run, request.region_name, request.aoi)
        _ensure_tool_trace(payload, _tool_trace_for_intent(intent, payload, request))
        _prepend_correction_trace(payload, correction_summary)
        return {
            "intent": intent,
            "mode": "adk",
            "response": payload,
        }
    if intent == "ACTION_COMMAND":
        payload = draft_action(request.message, run, request.user_id, request.region_name)
        _ensure_tool_trace(payload, _tool_trace_for_intent(intent, payload, request))
        _prepend_correction_trace(payload, correction_summary)
        return {
            "intent": intent,
            "mode": "adk",
            "response": payload,
        }
    if intent == "REPORT_REQUEST":
        result = create_report_for_run(run)
        _ensure_tool_trace(result, _tool_trace_for_intent(intent, result, request))
        _prepend_correction_trace(result, correction_summary)
        if result.get("status") == "success":
            result["answer"] = "Generated a fresh operations brief from the latest completed run."
            return {"intent": intent, "mode": "adk", "response": result, "report": result["report"]}
        return {"intent": intent, "mode": "adk", "response": result}
    if intent in {"CHANGE_EXPLANATION", "RISK_EXPLANATION", "OPERATIONAL_PRIORITIZATION"}:
        payload = answer_operational_question(request.message, run, request.region_name, request.aoi)
        _ensure_tool_trace(payload, _tool_trace_for_intent(intent, payload, request))
        _prepend_correction_trace(payload, correction_summary)
        return {
            "intent": intent,
            "mode": "adk",
            "response": payload,
        }
    payload = answer_operational_question(request.message, run, request.region_name, request.aoi)
    _ensure_tool_trace(payload, _tool_trace_for_intent("QUESTION", payload, request))
    _prepend_correction_trace(payload, correction_summary)
    return {"intent": intent, "mode": "adk", "response": payload}


def _resolve_run_for_request(request: ChatRequest) -> RunRecord | None:
    run = store.runs.get(request.run_id) if request.run_id else store.get_latest_run(request.region_id)
    if run is None and request.region_id == settings.demo_region_id:
        run = store.get_latest_run()
    return run


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
            "tool_trace": _tool_trace_for_analysis(artifacts.run),
        },
        "run": artifacts.run,
        "report": artifacts.report,
        "alert": artifacts.alert,
    }


def _operator_summary(run_record: RunRecord, report: dict, alert: dict | None) -> str:
    elastic = run_record.evidence.get("elastic", {})
    elastic_mode = elastic.get("mode", "unknown")
    elastic_items = elastic.get("evidence", [])
    if elastic_items:
        titles = ", ".join(str(item.get("title", "Elastic MCP evidence")) for item in elastic_items[:2])
        evidence_sentence = f"Elastic MCP evidence ({elastic_mode} mode) retrieved {titles}."
    else:
        evidence_sentence = f"Elastic MCP evidence ran in {elastic_mode} mode."
    alert_sentence = (
        "A high-risk alert was created for operator review."
        if alert
        else "No alert was created for this run."
    )
    return (
        f"{run_record.region_name} is currently {run_record.risk_level} at {run_record.risk_score}/100 "
        "after a chat-driven analysis. "
        f"{evidence_sentence} "
        f"The top recommendation is to {run_record.recommendations[0].lower()} "
        f"{report['title']} was generated and saved to the dashboard. {alert_sentence}"
    )


def _elastic_evidence_source(run_record: RunRecord) -> str:
    elastic = run_record.evidence.get("elastic", {})
    source = elastic.get("source") or "Elastic MCP"
    mode = elastic.get("mode", "unknown")
    return f"{source} ({mode} mode)"


def _should_correct_llm_route(classified_intent: str, runtime_intent: str) -> bool:
    if classified_intent == "QUESTION":
        return False
    expected_runtime_intent = {
        "ANALYZE_AND_REPORT": "ANALYZE_AND_REPORT",
        "WHAT_IF": "WHAT_IF",
        "ACTION_COMMAND": "ACTION_COMMAND",
        "REPORT_REQUEST": "REPORT_REQUEST",
        "CHANGE_EXPLANATION": "ANALYST_QA",
        "RISK_EXPLANATION": "ANALYST_QA",
        "OPERATIONAL_PRIORITIZATION": "ANALYST_QA",
    }.get(classified_intent)
    return bool(expected_runtime_intent and runtime_intent != expected_runtime_intent)


def _missing_tool_result(response: dict[str, Any]) -> bool:
    payload = response.get("response")
    return (
        isinstance(payload, dict)
        and payload.get("status") == "error"
        and "did not produce a structured response payload" in str(payload.get("answer", ""))
    )


def _needs_focus_aoi_fallback(response: dict[str, Any], request: ChatRequest, classified_intent: str) -> bool:
    if classified_intent not in {"CHANGE_EXPLANATION", "RISK_EXPLANATION", "OPERATIONAL_PRIORITIZATION", "QUESTION"}:
        return False
    if not (request.region_name and request.aoi):
        return False
    payload = response.get("response")
    if not isinstance(payload, dict):
        return False
    return payload.get("status") == "needs_context"


def _error_response(intent: str, message: str) -> dict[str, Any]:
    return {
        "intent": intent,
        "mode": "adk",
        "response": {
            "status": "error",
            "mode": "adk",
            "answer": message,
            "tool_trace": [
                _trace_item(
                    "Main Coordinator",
                    "Failed before selecting a workflow tool.",
                    message,
                    status="failed",
                )
            ],
        },
    }


def _ensure_tool_trace(payload: dict[str, Any], trace: list[dict[str, Any]]) -> None:
    payload.setdefault("tool_trace", trace)


def _prepend_correction_trace(payload: dict[str, Any], correction_summary: str | None) -> None:
    if not correction_summary:
        return
    trace = payload.setdefault("tool_trace", [])
    trace.insert(
        0,
        _trace_item(
            "Main Coordinator",
            "Applied deterministic guardrail.",
            correction_summary,
            status="completed",
        ),
    )


def _tool_trace_for_analysis(run_record: RunRecord) -> list[dict[str, Any]]:
    hotspots = run_record.evidence.get("hotspots", {})
    warnings = run_record.evidence.get("official_warnings", {})
    elastic = run_record.evidence.get("elastic", {})
    elastic_items = elastic.get("evidence", [])
    first_elastic_title = elastic_items[0].get("title") if elastic_items else "No Elastic evidence title"
    return [
        _trace_item("Main Coordinator", "Selected Analysis Workflow.", run_record.region_name),
        _trace_item(
            "External Data Tools",
            "Called hotspot, weather, warning, and exposure tools.",
            f"{hotspots.get('data', {}).get('count_24h', '--')} hotspots, "
            f"{warnings.get('data', {}).get('incident_count', 0)} warnings.",
        ),
        _trace_item(
            "Elastic MCP Tool",
            "Queried operational evidence.",
            f"{first_elastic_title} ({elastic.get('mode', 'unknown')} mode).",
            status="failed" if elastic.get("mode") == "fallback" else "completed",
        ),
        _trace_item(
            "Risk + Report Agents",
            "Computed risk score and generated report.",
            f"{run_record.risk_level} {run_record.risk_score}/100.",
        ),
    ]


def _tool_trace_for_intent(intent: str, payload: dict[str, Any], request: ChatRequest) -> list[dict[str, Any]]:
    if intent == "WHAT_IF":
        scenario = payload.get("scenario", {})
        baseline = payload.get("baseline", {})
        scenario_delta = payload.get("scenario_delta") or scenario.get("delta") or {}
        scenario_level = scenario.get("risk_level", scenario.get("qualitative_risk", "scenario pending"))
        return [
            _trace_item("Main Coordinator", "Selected What-if Agent.", request.region_name or request.region_id),
            _trace_item("Scenario Parser", "Parsed scenario request.", str(scenario_delta)),
            _trace_item(
                "Risk Engine",
                "Computed baseline and scenario.",
                f"{baseline.get('risk_level', 'baseline pending')} -> {scenario_level}.",
            ),
        ]
    if intent == "ACTION_COMMAND":
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
    if intent == "REPORT_REQUEST":
        report = payload.get("report", {})
        return [
            _trace_item("Main Coordinator", "Selected Report Agent.", "Report request."),
            _trace_item(
                "Report Agent",
                "Generated report from latest run.",
                report.get("title", payload.get("message", "Report pending.")),
            ),
        ]
    return [
        _trace_item("Main Coordinator", "Selected Analyst Agent.", request.region_name or request.region_id),
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


def _get_session_service() -> InMemorySessionService:
    global _SESSION_SERVICE
    if _SESSION_SERVICE is None:
        _SESSION_SERVICE = InMemorySessionService()
    return _SESSION_SERVICE


def _get_runner() -> Runner:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = Runner(
            app_name=APP_NAME,
            agent=root_agent,
            session_service=_get_session_service(),
        )
    return _RUNNER


async def _ensure_session(session_service: InMemorySessionService, user_id: str, session_id: str) -> None:
    existing = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    if existing is None:
        await session_service.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id, state={})


async def _merge_request_state(
    session_service: InMemorySessionService,
    user_id: str,
    session_id: str,
    request: ChatRequest,
) -> None:
    session = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    if session is not None:
        session.state.update(_state_delta_for_request(request))


def _state_delta_for_request(request: ChatRequest) -> dict[str, Any]:
    delta: dict[str, Any] = {
        "app:run_id": request.run_id,
        "app:region_id": request.region_id,
        "app:region_name": request.region_name,
        "app:user_id": request.user_id,
        "app:last_request_message": request.message,
        "last_intent": None,
        "last_response_payload": None,
        "last_run_id": None,
        "last_report_id": None,
        "last_alert_id": None,
        "last_action_id": None,
    }
    if request.aoi and request.aoi.center:
        delta["app:aoi_center"] = list(request.aoi.center)
        delta["app:aoi_radius_km"] = request.aoi.radius_km
    else:
        delta["app:aoi_center"] = None
        delta["app:aoi_radius_km"] = None
    return delta


def _message_with_operational_context(request: ChatRequest) -> str:
    context: dict[str, Any] = {
        "region_id": request.region_id,
        "region_name": request.region_name,
        "user_id": request.user_id,
        "run_id": request.run_id,
    }
    if request.aoi and request.aoi.center:
        context["aoi_center"] = list(request.aoi.center)
        context["radius_km"] = request.aoi.radius_km
    return (
        f"Operator request: {request.message}\n"
        f"Deterministic safety classifier intent hint: {classify_intent(request.message)}\n"
        f"Focus AOI context for workflow tools: {context}\n"
        "When calling a workflow tool, pass the operator request and any available "
        "region_id, region_name, aoi_center, radius_km, run_id, and user_id values."
    )


def _session_id_for(request: ChatRequest) -> str:
    if request.run_id:
        return f"run:{request.run_id}"
    region = request.region_id or settings.demo_region_id
    return f"{request.user_id}:{region}"


def _ensure_vertex_configuration() -> None:
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION")
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is not set for Vertex AI.")
    if not location:
        raise RuntimeError("GOOGLE_CLOUD_LOCATION is not set for Vertex AI.")
    try:
        google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    except DefaultCredentialsError as exc:
        raise RuntimeError(str(exc)) from exc


def _extract_text(content: types.Content | None) -> str | None:
    parts = getattr(content, "parts", None)
    if not content or not parts:
        return None
    chunks: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            chunks.append(text)
    return "\n".join(chunks).strip() or None


def _build_runtime_response(
    request: ChatRequest,
    state: dict[str, Any],
    final_text: str | None,
) -> dict[str, Any]:
    classified_intent = classify_intent(request.message)
    intent = _public_intent(str(state.get("last_intent") or classified_intent), classified_intent)
    payload = state.get("last_response_payload")
    if not isinstance(payload, dict):
        payload = {
            "status": "error",
            "mode": "adk",
            "answer": final_text or "The ADK runtime did not produce a structured response payload.",
        }
    else:
        payload = dict(payload)
        payload.setdefault("mode", "adk")
        if final_text:
            payload["answer"] = final_text

    run = _lookup_store_item(store.runs, state.get("last_run_id"))
    report = _lookup_store_item(store.reports, state.get("last_report_id"))
    alert = _lookup_store_item(store.alerts, state.get("last_alert_id"))

    if intent == "REPORT_REQUEST" and report is None:
        run_for_report = run or store.get_latest_run(request.region_id)
        report_payload = create_report_for_run(run_for_report)
        if report_payload.get("status") == "success":
            report = report_payload["report"]
            payload |= report_payload

    response: dict[str, Any] = {
        "intent": intent,
        "mode": "adk",
        "response": payload,
    }
    if run is not None:
        response["run"] = run
    if report is not None:
        response["report"] = report
    if alert is not None:
        response["alert"] = alert
    return response


def _lookup_store_item(items: dict[str, Any], key: Any) -> Any | None:
    if not key:
        return None
    return items.get(str(key))


def _public_intent(runtime_intent: str, classified_intent: str) -> str:
    if classified_intent != "QUESTION":
        return classified_intent
    return runtime_intent
