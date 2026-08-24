from __future__ import annotations

import asyncio
import json
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
from app.services.agent_events import new_trace_id, publish_agent_event
from app.services.chat_conversations import (
    analysis_required_response,
    finalize_chat_response,
    prepare_conversation,
    should_block_for_analysis,
)
from app.services.conversation_memory import lookup_conversation_memory, memory_operation_for_message
from app.services.deterministic_calculator import calculation_response_from_message
from app.services.firestore_store import store
from app.services.hotspot_visualization import build_hotspot_visualization
from app.services.monitoring_tasks import create_monitor_task_from_chat
from app.services.request_scope import is_wildfire_operations_request, out_of_scope_response
from app.services.timing_trace import TimingTrace
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
        timing = TimingTrace()
        with timing.step("scope_gate"):
            in_scope = is_wildfire_operations_request(request)
        if not in_scope:
            return _attach_timing_trace(out_of_scope_response(mode="adk"), timing, "OUT_OF_SCOPE")
        with timing.step("prepare_conversation"):
            conversation, request = prepare_conversation(request)
        trace_id = new_trace_id()
        with timing.step("classify_intent"):
            intent = classify_intent(request.message)
        _publish_chat_event(
            trace_id, request, conversation.conversation_id, "started", "Coordinator received chat request.", intent
        )
        _publish_chat_event(
            trace_id, request, conversation.conversation_id, "completed", f"Intent classified: {intent}.", intent
        )
        with timing.step("analysis_gate", intent=intent):
            blocked_for_analysis = should_block_for_analysis(intent, request, conversation)
        if blocked_for_analysis:
            _publish_chat_event(
                trace_id,
                request,
                conversation.conversation_id,
                "blocked",
                "Analysis gate blocked request before workflow tool calls.",
                intent,
            )
            response = analysis_required_response(request, conversation, intent, mode="adk", trace_id=trace_id)
            return _attach_timing_trace(response, timing, intent)
        _publish_chat_event(
            trace_id, request, conversation.conversation_id, "completed", "Analysis gate passed.", intent
        )
        try:
            with timing.step("adk_setup", intent=intent):
                _ensure_vertex_configuration()
                session_service = _get_session_service()
                runner = _get_runner()
                user_id = request.user_id or "demo_officer"
                session_id = _session_id_for(request)
                await _ensure_session(session_service, user_id, session_id)
                await _merge_request_state(session_service, user_id, session_id, request)

            with timing.step("adk_llm_call", intent=intent):
                final_text = await _run_llm_turn_with_retries(
                    lambda: runner.run_async(
                        user_id=user_id,
                        session_id=session_id,
                        new_message=types.Content(
                            role="user",
                            parts=[types.Part(text=_message_with_operational_context(request))],
                        ),
                        state_delta=_state_delta_for_request(request),
                    )
                )

            with timing.step("adk_session_read", intent=intent):
                session = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
                session_state = session.state if session else {}
                runtime_intent = str(session_state.get("last_intent") or "")
            if not runtime_intent:
                if intent in {"ACTION_COMMAND", "CALCULATION", "KNOWLEDGE_REQUIRED", "MEMORY_LOOKUP"}:
                    with timing.step("tool_call", intent=intent, tool="action_fallback_no_llm_tool"):
                        fallback = _route_deterministic_workflow(
                            request,
                            intent,
                            correction_summary=(
                                "Deterministic fallback ran because Gemini did not call the required tool."
                            ),
                        )
                    if fallback is not None:
                        fallback["trace_id"] = trace_id
                        return _finalize_chat_response_timed(request, conversation, fallback, timing)
                return _finalize_chat_response_timed(
                    request,
                    conversation,
                    _with_trace_id(
                        _error_response(
                            "ROUTING_FAILED",
                            "The coordinator did not call a required deterministic or RAG-handoff tool. No answer "
                            "was generated from model memory.",
                        ),
                        trace_id,
                    ),
                    timing,
                )
            elif _should_correct_llm_route(intent, runtime_intent):
                with timing.step("tool_call", intent=intent, tool="corrected_deterministic_workflow"):
                    corrected = _route_deterministic_workflow(
                        request,
                        intent,
                        correction_summary=(
                            f"Deterministic guardrail corrected route from "
                            f"{runtime_intent or 'no tool call'} to {intent}."
                        ),
                    )
                if corrected is not None:
                    corrected["trace_id"] = trace_id
                    return _finalize_chat_response_timed(request, conversation, corrected, timing)

            with timing.step("build_runtime_response", intent=intent, runtime_intent=runtime_intent):
                response = _build_runtime_response(request, session_state, final_text)
            if intent == "ACTION_COMMAND" and _missing_action_payload(response):
                with timing.step("tool_call", intent=intent, tool="action_fallback_missing_payload"):
                    fallback = _route_deterministic_workflow(
                        request,
                        intent,
                        correction_summary=(
                            "Deterministic fallback ran because Gemini did not return an action approval payload."
                        ),
                    )
                if fallback is not None:
                    fallback["trace_id"] = trace_id
                    return _finalize_chat_response_timed(request, conversation, fallback, timing)
            if _missing_tool_result(response):
                if intent in {"ACTION_COMMAND", "CALCULATION", "KNOWLEDGE_REQUIRED", "MEMORY_LOOKUP"}:
                    with timing.step("tool_call", intent=intent, tool="action_fallback_missing_tool_result"):
                        fallback = _route_deterministic_workflow(
                            request,
                            intent,
                            correction_summary=(
                                "Deterministic fallback ran because Gemini did not return a required tool payload."
                            ),
                        )
                    if fallback is not None:
                        fallback["trace_id"] = trace_id
                        return _finalize_chat_response_timed(request, conversation, fallback, timing)
                return _finalize_chat_response_timed(
                    request,
                    conversation,
                    _with_trace_id(
                        _error_response(
                            intent,
                            "Gemini/Vertex AI did not produce a structured tool payload or final text.",
                        ),
                        trace_id,
                    ),
                    timing,
                )
            if _needs_focus_aoi_fallback(response, request, intent):
                return _finalize_chat_response_timed(
                    request,
                    conversation,
                    _with_trace_id(
                        _error_response(
                            intent,
                            "Gemini/Vertex AI did not answer from the selected AOI context. Retry the question.",
                        ),
                        trace_id,
                    ),
                    timing,
                )
            response["trace_id"] = trace_id
            return _finalize_chat_response_timed(request, conversation, response, timing)
        except Exception as exc:
            if _is_resource_exhausted_error(exc):
                return _finalize_chat_response_timed(
                    request,
                    conversation,
                    _with_trace_id(_error_response(intent, f"Gemini/Vertex AI runtime failed: {exc}"), trace_id),
                    timing,
                )
            if intent in {"ACTION_COMMAND", "CALCULATION", "KNOWLEDGE_REQUIRED", "MEMORY_LOOKUP"}:
                with timing.step("tool_call", intent=intent, tool="action_safety_fallback"):
                    fallback = _route_deterministic_workflow(
                        request,
                        intent,
                        correction_summary=f"Safety fallback ran because ADK runtime failed: {exc}",
                    )
                if fallback is not None:
                    fallback["trace_id"] = trace_id
                    return _finalize_chat_response_timed(request, conversation, fallback, timing)
            return _finalize_chat_response_timed(
                request,
                conversation,
                _with_trace_id(_error_response(intent, f"ADK runtime failed: {exc}"), trace_id),
                timing,
            )


def _finalize_chat_response_timed(
    request: ChatRequest,
    conversation: Any,
    response: dict[str, Any],
    timing: TimingTrace,
) -> dict[str, Any]:
    with timing.step("finalize_response", intent=response.get("intent")):
        finalized = finalize_chat_response(request, conversation, response)
    return _attach_timing_trace(finalized, timing, str(finalized.get("intent") or response.get("intent") or "UNKNOWN"))


def _attach_timing_trace(response: dict[str, Any], timing: TimingTrace, intent: str) -> dict[str, Any]:
    trace = timing.snapshot()
    trace["intent"] = intent
    response["timing_trace"] = trace
    return response


def _route_deterministic_workflow(
    request: ChatRequest,
    intent: str,
    correction_summary: str | None = None,
) -> dict[str, Any] | None:
    run = _resolve_run_for_request(request)
    if intent == "MEMORY_LOOKUP":
        operation = memory_operation_for_message(request.message)
        if operation is None:
            return _error_response(intent, "No supported deterministic memory lookup matched this request.")
        payload = lookup_conversation_memory(request, operation)
        _prepend_correction_trace(payload, correction_summary)
        return {"intent": intent, "mode": "adk", "response": payload}
    if intent == "CALCULATION":
        payload = calculation_response_from_message(request.message, mode="adk")
        _prepend_correction_trace(payload, correction_summary)
        return {"intent": intent, "mode": "adk", "response": payload}
    if intent == "KNOWLEDGE_REQUIRED":
        payload = _knowledge_required_response(request.message)
        _prepend_correction_trace(payload, correction_summary)
        return {"intent": intent, "mode": "adk", "response": payload}
    if intent == "ANALYZE_AND_REPORT":
        response = _analyze_and_report(request)
        _prepend_correction_trace(response["response"], correction_summary)
        return response
    if intent == "HOTSPOT_VISUALIZATION":
        payload = _hotspot_visualization_response(request)
        _prepend_correction_trace(payload, correction_summary)
        return {"intent": intent, "mode": "adk", "response": payload}
    if intent == "MONITOR_TASK":
        payload = create_monitor_task_from_chat(request)
        _prepend_correction_trace(payload, correction_summary)
        return {"intent": intent, "mode": "adk", "response": payload}
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
    if intent in {
        "CHANGE_EXPLANATION",
        "WEATHER_CHANGE",
        "WIND_CHANGE",
        "RISK_EXPLANATION",
        "OPERATIONAL_PRIORITIZATION",
        "EXPOSURE_LOOKUP",
        "QUESTION",
    }:
        return _route_local_analyst_synthesis(request, intent, correction_summary=correction_summary)
    return _error_response(intent, "Gemini/Vertex AI did not return a usable response.")


def _with_trace_id(response: dict[str, Any], trace_id: str) -> dict[str, Any]:
    response["trace_id"] = trace_id
    return response


def _route_local_analyst_synthesis(
    request: ChatRequest,
    intent: str,
    correction_summary: str | None = None,
) -> dict[str, Any] | None:
    if intent not in {
        "CHANGE_EXPLANATION",
        "WEATHER_CHANGE",
        "WIND_CHANGE",
        "RISK_EXPLANATION",
        "OPERATIONAL_PRIORITIZATION",
        "EXPOSURE_LOOKUP",
        "QUESTION",
    }:
        return None
    run = _resolve_run_for_request(request)
    payload = answer_operational_question(request.message, run, request.region_name, request.aoi)
    payload["mode"] = "adk"
    _ensure_tool_trace(payload, _tool_trace_for_intent(intent, payload, request))
    _prepend_correction_trace(payload, correction_summary)
    if payload.get("requires_synthesis"):
        _apply_synthesis_answer(payload, None, request)
    response: dict[str, Any] = {"intent": intent, "mode": "adk", "response": payload}
    if run:
        response["run"] = run
    return response


def _knowledge_required_response(message: str) -> dict[str, Any]:
    return {
        "status": "knowledge_required",
        "mode": "adk",
        "answer": (
            "This wildfire question requires verified document retrieval, but the production RAG pipeline is not "
            "enabled in this phase. I will not answer from model memory."
        ),
        "requires_rag": True,
        "query": message,
        "tool_trace": [
            _trace_item(
                "Knowledge Retrieval Required",
                "Stopped before generation because no deterministic tool can answer the request.",
                "Verified document retrieval is required.",
                status="blocked",
            )
        ],
    }


async def _run_llm_turn_with_retries(run_factory: Any) -> str | None:
    attempts = int(os.getenv("ADK_GEMINI_RETRY_ATTEMPTS", "3"))
    base_delay = float(os.getenv("ADK_GEMINI_RETRY_BASE_DELAY_SECONDS", "1.0"))
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            final_text: str | None = None
            async for event in run_factory():
                if event.is_final_response():
                    text = _extract_text(event.content)
                    if text:
                        final_text = text
            return final_text
        except Exception as exc:
            last_error = exc
            if not _is_resource_exhausted_error(exc) or attempt >= attempts - 1:
                raise
            await asyncio.sleep(base_delay * (2**attempt))
    if last_error:
        raise last_error
    return None


def _is_resource_exhausted_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "resource_exhausted" in text or "resource has been exhausted" in text


async def _run_llm_repair_answer(
    runner: Runner,
    user_id: str,
    session_id: str,
    request: ChatRequest,
    reason: str,
) -> str | None:
    return await _run_llm_turn_with_retries(
        lambda: runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part(text=_repair_message_with_operational_context(request, reason))],
            ),
            state_delta={},
        )
    )


def _llm_repair_response(intent: str, answer: str) -> dict[str, Any]:
    return {
        "intent": intent,
        "mode": "adk",
        "response": {
            "status": "success",
            "mode": "adk",
            "answer": answer,
            "tool_trace": [
                _trace_item(
                    "Main Coordinator",
                    "Recovered with Gemini repair answer.",
                    (
                        "Gemini/Vertex AI produced a fallback answer after the initial ADK turn returned no usable "
                        "payload."
                    ),
                )
            ],
        },
    }


def _publish_chat_event(
    trace_id: str,
    request: ChatRequest,
    conversation_id: str,
    status: str,
    message: str,
    intent: str,
) -> None:
    publish_agent_event(
        trace_id=trace_id,
        conversation_id=conversation_id,
        run_id=request.run_id,
        region_id=request.region_id,
        agent_type="coordinator",
        status=status,
        message=message,
        data={"intent": intent, "mode": "adk"},
    )


def _publish_artifact_event(
    trace_id: str,
    request: ChatRequest,
    conversation_id: str,
    agent_type: str,
    message: str,
    intent: str,
) -> None:
    publish_agent_event(
        trace_id=trace_id,
        conversation_id=conversation_id,
        run_id=request.run_id,
        region_id=request.region_id,
        agent_type=agent_type,
        status="completed",
        message=message,
        data={"intent": intent, "mode": "adk"},
    )


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
    hotspots = run_record.evidence.get("hotspots", {})
    hotspot_count = hotspots.get("data", {}).get("count_24h")
    weather = run_record.evidence.get("weather", {})
    weather_data = weather.get("data", {})
    warnings = run_record.evidence.get("official_warnings", {})
    warning_count = warnings.get("data", {}).get("incident_count")
    evidence_parts = []
    if hotspot_count is not None:
        evidence_parts.append(f"the hotspot tool found {hotspot_count} detections in the last 24 hours")
    if weather_data:
        evidence_parts.append(
            "the weather tool shows "
            f"{weather_data.get('wind_gust_max', 'unknown')} km/h gusts, "
            f"{weather_data.get('humidity_min', 'unknown')}% minimum humidity, and "
            f"{weather_data.get('rainfall_7d', 'unknown')} mm seven-day rainfall"
        )
    if warning_count is not None:
        evidence_parts.append(f"the warnings tool found {warning_count} nearby official warnings")
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


def _elastic_evidence_source(run_record: RunRecord) -> str:
    elastic = run_record.evidence.get("elastic", {})
    source = elastic.get("source") or "Elastic MCP"
    mode = elastic.get("mode", "unknown")
    return f"{source} ({mode} mode)"


def _should_correct_llm_route(classified_intent: str, runtime_intent: str) -> bool:
    if classified_intent == "ACTION_COMMAND":
        return runtime_intent not in {
            "ACTION_COMMAND",
            "EXPOSURE_ACTION",
        }
    return classified_intent in {
        "CHANGE_EXPLANATION",
        "WEATHER_CHANGE",
        "WIND_CHANGE",
        "RISK_EXPLANATION",
        "OPERATIONAL_PRIORITIZATION",
        "EXPOSURE_LOOKUP",
        "QUESTION",
    } and runtime_intent == "KNOWLEDGE_REQUIRED"


def _missing_tool_result(response: dict[str, Any]) -> bool:
    payload = response.get("response")
    return (
        isinstance(payload, dict)
        and payload.get("status") == "error"
        and "did not produce a structured response payload" in str(payload.get("answer", ""))
    )


def _missing_action_payload(response: dict[str, Any]) -> bool:
    payload = response.get("response")
    return not (
        isinstance(payload, dict)
        and isinstance(payload.get("action"), dict)
        and isinstance(payload.get("approval"), dict)
    )


def _needs_focus_aoi_fallback(response: dict[str, Any], request: ChatRequest, classified_intent: str) -> bool:
    if classified_intent not in {
        "CHANGE_EXPLANATION",
        "WEATHER_CHANGE",
        "WIND_CHANGE",
        "RISK_EXPLANATION",
        "OPERATIONAL_PRIORITIZATION",
        "EXPOSURE_LOOKUP",
        "QUESTION",
    }:
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


def _allows_context_answer(intent: str) -> bool:
    return intent in {"QUESTION", "CHANGE_EXPLANATION", "RISK_EXPLANATION", "OPERATIONAL_PRIORITIZATION"}


def _context_answer_response(
    request: ChatRequest,
    final_text: str | None,
    reason: str,
    *,
    status: str = "success",
) -> dict[str, Any]:
    run = _resolve_run_for_request(request)
    if not final_text:
        return _error_response(
            "CONTEXT_ANSWER",
            "Gemini/Vertex AI did not return an answer from the provided context.",
        )
    trace_status = "completed" if status == "success" else "failed"
    return {
        "intent": "CONTEXT_ANSWER",
        "mode": "adk",
        "response": {
            "status": status,
            "mode": "adk",
            "answer": final_text,
            "tool_trace": [
                _trace_item(
                    "Context JSON",
                    "Answered without workflow tool calls.",
                    reason,
                    status=trace_status,
                )
            ],
            "tool_results": {
                "context_source": "conversation_summary_latest_analysis_elastic",
                "run_id": run.run_id if run else None,
                "elastic_mode": run.evidence.get("elastic", {}).get("mode") if run else None,
            },
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
    if intent == "HOTSPOT_VISUALIZATION":
        visualization = payload.get("visualization", {})
        return [
            _trace_item(
                "Main Coordinator",
                "Selected Hotspot Visualization Workflow.",
                visualization.get("region", {}).get("region_name", request.region_name or request.region_id),
            ),
            _trace_item(
                "Hotspot Density Tool",
                "Computed heatmap cells.",
                f"{len(visualization.get('heatmap', {}).get('cells', []))} cells",
            ),
            _trace_item(
                "Contour Tool",
                "Generated contour GeoJSON.",
                f"{len(visualization.get('contours', {}).get('features', []))} contour bands",
            ),
        ]
    if intent == "MONITOR_TASK":
        task = payload.get("monitor_task", {})
        return [
            _trace_item(
                "Main Coordinator",
                "Selected Monitor Task Workflow.",
                task.get("region_name", request.region_name),
            ),
            _trace_item(
                "Monitoring Scheduler",
                "Created recurring risk check.",
                f"{task.get('interval_minutes', 10)} minute interval",
            ),
            _trace_item("Alert Rule", "Configured material-change alerting.", "score delta >= 12"),
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
    _ensure_tool_trace(payload, _tool_trace_for_intent("HOTSPOT_VISUALIZATION", payload, request))
    return payload


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
        "app:conversation_id": request.conversation_id,
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
    context = _context_json_for_request(request)
    conversation = store.conversations.get(request.conversation_id or "")
    compressed_context = conversation.compressed_context if conversation else ""
    return (
        f"Operator request: {request.message}\n"
        f"context_json: {json.dumps(context, default=str)}\n"
        f"Compressed conversation context: {compressed_context or 'none'}\n"
        "Select exactly one provided tool. Prefer a deterministic workflow or calculation tool whenever it can "
        "answer the exact request. Never answer directly from context_json or model memory. Use "
        "conversation_memory_lookup_tool for exact prior-question, selected-AOI, report-AOI, or action-status "
        "state. Use analyst_question_tool for operational evidence synthesis. Use "
        "knowledge_retrieval_required_tool when no deterministic tool can answer; do not invent a knowledge answer. "
        "When a tool returns structured evidence, synthesize the final answer for the exact requested dimension. "
        "If the evidence packet includes missing baseline data, say what is missing instead of answering a nearby "
        "question. "
        "When calling a workflow tool, pass the operator request and any available region_id, region_name, "
        "aoi_center, radius_km, run_id, and user_id values."
    )


def _repair_message_with_operational_context(request: ChatRequest, reason: str) -> str:
    context = _context_json_for_request(request)
    conversation = store.conversations.get(request.conversation_id or "")
    compressed_context = conversation.compressed_context if conversation else ""
    intent = classify_intent(request.message)
    return (
        "The previous ADK turn failed to produce a usable operator response.\n"
        f"Failure reason: {reason}\n"
        f"Operator request: {request.message}\n"
        f"Intent hint: {intent}\n"
        f"context_json: {json.dumps(context, default=str)}\n"
        f"Compressed conversation context: {compressed_context or 'none'}\n"
        "Produce one concise operator-facing answer using only the supplied context_json and conversation context. "
        "Do not call tools in this repair turn. If a required workflow tool did not run, do not claim that an action, "
        "report, monitor, visualization, or analysis was created. Instead explain what failed and what the operator "
        "can safely infer from the available context. For inspection-priority or risk questions, answer directly from "
        "latest_run recommendations, evidence, and selected_aoi when available. If the supplied context is "
        "insufficient, "
        "say exactly what is missing."
    )


def _context_json_for_request(request: ChatRequest) -> dict[str, Any]:
    run = _resolve_run_for_request(request)
    selected_aoi: dict[str, Any] = {
        "region_id": request.region_id,
        "region_name": request.region_name,
        "run_id": request.run_id,
        "conversation_id": request.conversation_id,
    }
    if request.aoi and request.aoi.center:
        selected_aoi["center"] = list(request.aoi.center)
        selected_aoi["radius_km"] = request.aoi.radius_km
    latest_run = None
    evidence_summary = {}
    if run:
        latest_run = {
            "run_id": run.run_id,
            "region_id": run.region_id,
            "region_name": run.region_name,
            "risk_score": run.risk_score,
            "risk_level": run.risk_level,
            "drivers": run.risk_assessment.get("drivers", []),
            "recommendations": run.recommendations,
        }
        region_context = run.evidence.get("region_context", {})
        if region_context:
            selected_aoi.setdefault("center", region_context.get("center"))
            selected_aoi.setdefault("radius_km", region_context.get("radius_km"))
        elastic = run.evidence.get("elastic", {})
        evidence_summary = {
            "region_context": region_context,
            "hotspots": run.evidence.get("hotspots", {}).get("data", {}),
            "weather": run.evidence.get("weather", {}).get("data", {}),
            "spatial": run.evidence.get("spatial", {}).get("data", {}),
            "official_warnings": run.evidence.get("official_warnings", {}).get("data", {}),
            "elastic": {
                "mode": elastic.get("mode"),
                "evidence": elastic.get("evidence", [])[:3],
            },
        }
    return {
        "selected_aoi": selected_aoi,
        "latest_run": latest_run,
        "evidence": evidence_summary,
    }


def _session_id_for(request: ChatRequest) -> str:
    if request.conversation_id:
        return f"conversation:{request.conversation_id}"
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
        if payload.get("requires_synthesis"):
            _apply_synthesis_answer(payload, final_text, request)

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


def _apply_synthesis_answer(payload: dict[str, Any], final_text: str | None, request: ChatRequest) -> None:
    if final_text and _valid_synthesis_answer(final_text, payload):
        payload["answer"] = final_text
        payload["synthesis_source"] = "llm"
        return
    payload["answer"] = _safe_synthesis_answer(payload, request)
    payload["synthesis_source"] = "validator"
    trace = payload.setdefault("tool_trace", [])
    trace.append(
        _trace_item(
            "Response Validator",
            "Validated final answer against requested dimension.",
            "LLM final text was missing or off-target; returned structured evidence synthesis.",
            status="completed",
        )
    )


def _valid_synthesis_answer(answer: str, payload: dict[str, Any]) -> bool:
    lowered = answer.lower()
    question_type = str(payload.get("question_type") or "")
    if payload.get("missing") and not any(
        term in lowered
        for term in ["missing", "cannot", "can't", "do not have", "don't have", "need", "no baseline"]
    ):
        return False
    if question_type == "wind_change":
        return "wind" in lowered and any(
            term in lowered for term in ["yesterday", "baseline", "previous", "missing"]
        )
    if question_type == "weather_change":
        return "weather" in lowered and any(
            term in lowered for term in ["yesterday", "baseline", "previous", "missing"]
        )
    if question_type == "overall_change":
        return any(term in lowered for term in ["changed", "change", "yesterday", "baseline", "previous"])
    if question_type == "exposure_lookup":
        return any(term in lowered for term in ["asset", "protected", "park", "road", "town", "settlement"])
    return bool(answer.strip())


def _safe_synthesis_answer(payload: dict[str, Any], request: ChatRequest) -> str:
    question_type = str(payload.get("question_type") or "operational_summary")
    raw_facts = payload.get("facts")
    facts: dict[str, Any] = raw_facts if isinstance(raw_facts, dict) else {}
    raw_current = facts.get("current")
    current: dict[str, Any] = raw_current if isinstance(raw_current, dict) else {}
    raw_previous = facts.get("previous")
    previous: dict[str, Any] | None = raw_previous if isinstance(raw_previous, dict) else None
    raw_deltas = facts.get("deltas")
    deltas: dict[str, Any] = raw_deltas if isinstance(raw_deltas, dict) else {}
    missing = [str(item) for item in payload.get("missing", [])]
    region = current.get("region_name") or request.region_name or request.region_id or "the selected AOI"
    if payload.get("status") == "missing_context" and not current:
        missing_text = ", ".join(missing) or "completed analysis context"
        return f"I need {missing_text} before I can answer this operational question for {region}."
    if question_type == "wind_change":
        return _wind_change_answer(region, current, previous, deltas, missing)
    if question_type == "weather_change":
        return _weather_change_answer(region, current, previous, deltas, missing)
    if question_type == "overall_change":
        return _overall_change_answer(region, current, previous, deltas, missing)
    if question_type == "exposure_lookup":
        return _exposure_lookup_answer(region, current)
    if question_type == "inspection_priority":
        recommendations = payload.get("recommendations") or []
        first = str(recommendations[0]) if recommendations else "inspect the densest active hotspot cluster first"
        return (
            f"For {region}, inspect this first: {first}. This is based on the latest run drivers and spatial exposure "
            "evidence."
        )
    if question_type == "risk_explanation":
        drivers = _driver_names(current)
        risk = _risk_text(current)
        return (
            f"{region} is {risk}. The leading drivers are {drivers}, supported by the latest hotspot, weather, "
            "spatial, and Elastic evidence."
        )
    return f"{region} is {_risk_text(current)} based on the latest completed analysis run."


def _wind_change_answer(
    region: str,
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    deltas: dict[str, Any],
    missing: list[str],
) -> str:
    current_wind = current.get("weather", {}).get("wind_gust_kmh")
    delta = deltas.get("wind_gust_kmh")
    if missing or not previous or not delta:
        missing_text = ", ".join(missing or ["yesterday wind baseline"])
        current_text = f" Current wind gust evidence is {current_wind} km/h." if current_wind is not None else ""
        return (
            f"I cannot calculate how wind changed since yesterday for {region} because {missing_text} is "
            f"missing.{current_text}"
        )
    return (
        f"Wind changed since yesterday in {region}: gusts are {delta['current']:g} km/h now versus "
        f"{delta['previous']:g} km/h previously, a {delta['delta']:+g} km/h change."
    )


def _weather_change_answer(
    region: str,
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    deltas: dict[str, Any],
    missing: list[str],
) -> str:
    if missing or not previous:
        missing_text = ", ".join(missing or ["yesterday matched completed analysis run"])
        weather = current.get("weather", {})
        return (
            f"I cannot calculate weather change since yesterday for {region} because {missing_text} is missing. "
            f"Current evidence shows wind gusts {weather.get('wind_gust_kmh', 'unknown')} km/h, "
            f"minimum humidity {weather.get('humidity_min', 'unknown')}%, and seven-day rainfall "
            f"{weather.get('rainfall_7d', 'unknown')} mm."
        )
    wind = deltas.get("wind_gust_kmh")
    humidity = deltas.get("humidity_min")
    parts = []
    if wind:
        parts.append(f"wind gusts {wind['delta']:+g} km/h")
    if humidity:
        parts.append(f"minimum humidity {humidity['delta']:+g} points")
    return (
        f"Weather changed since yesterday in {region}: "
        f"{', '.join(parts) or 'no comparable weather deltas were available'}."
    )


def _overall_change_answer(
    region: str,
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    deltas: dict[str, Any],
    missing: list[str],
) -> str:
    if missing or not previous:
        missing_text = ", ".join(missing or ["yesterday matched completed analysis run"])
        return (
            f"I cannot compute what changed since yesterday for {region} because {missing_text} is missing. "
            f"The current run shows {_risk_text(current)} with leading drivers {_driver_names(current)}."
        )
    risk_delta = deltas.get("risk_score")
    hotspot_delta = deltas.get("hotspot_count_24h")
    parts = []
    if risk_delta:
        parts.append(f"risk score {risk_delta['previous']:g} -> {risk_delta['current']:g} ({risk_delta['delta']:+g})")
    if hotspot_delta:
        parts.append(
            f"24h hotspots {hotspot_delta['previous']:g} -> {hotspot_delta['current']:g} ({hotspot_delta['delta']:+g})"
        )
    return f"Since yesterday in {region}, {', '.join(parts) or 'no comparable numeric deltas were available'}."


def _exposure_lookup_answer(region: str, current: dict[str, Any]) -> str:
    spatial = current.get("spatial", {})
    critical_assets = [str(item) for item in spatial.get("critical_assets", [])]
    protected_areas = [str(item) for item in spatial.get("protected_areas", [])]
    critical_text = _format_items(critical_assets, "no named critical assets returned")
    protected_text = _format_items(protected_areas, "no named protected or park areas returned")
    return (
        f"For {region}, spatial evidence returned {spatial.get('critical_asset_count', 0)} critical assets and "
        f"{spatial.get('protected_area_count', 0)} protected or park areas. Critical assets: {critical_text}. "
        f"Protected/park areas: {protected_text}. The current exposure tool does not enumerate named road corridors or "
        "town/settlement assets, so I will not claim specific roads or towns from this evidence."
    )


def _risk_text(current: dict[str, Any]) -> str:
    level = current.get("risk_level") or "unknown risk"
    score = current.get("risk_score")
    return f"{level} at {score}/100" if score is not None else str(level)


def _driver_names(current: dict[str, Any]) -> str:
    drivers = current.get("drivers", [])
    names = [str(item.get("factor")) for item in drivers if isinstance(item, dict) and item.get("factor")]
    return ", ".join(names[:3]) if names else "no dominant drivers"


def _format_items(items: list[str], empty: str) -> str:
    if not items:
        return empty
    visible = items[:5]
    suffix = f", plus {len(items) - len(visible)} more" if len(items) > len(visible) else ""
    return "; ".join(visible) + suffix


def _lookup_store_item(items: dict[str, Any], key: Any) -> Any | None:
    if not key:
        return None
    return items.get(str(key))


def _public_intent(runtime_intent: str, classified_intent: str) -> str:
    if runtime_intent == "ANALYST_QA" and classified_intent != "QUESTION":
        return classified_intent
    return runtime_intent
