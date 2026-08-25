"""Final response assembly and validation for the ADK runtime.

Turns raw ADK session state (or a routing failure) into the response shape
the rest of the app expects, and validates/repairs the LLM's final text
against the deterministic synthesis in app.runtime.adk.synthesis.
"""

from __future__ import annotations

from typing import Any

from app.agents.specialists.report_agent import create_report_for_run
from app.models.schemas import ChatRequest, RunRecord
from app.runtime.adk.synthesis import _safe_synthesis_answer
from app.runtime.intent_responses import trace_item
from app.runtime.intents import classify_intent
from app.services.chat_conversations import finalize_chat_response
from app.services.firestore_store import store
from app.services.timing_trace import TimingTrace


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


def _with_trace_id(response: dict[str, Any], trace_id: str) -> dict[str, Any]:
    response["trace_id"] = trace_id
    return response


def _error_response(intent: str, message: str) -> dict[str, Any]:
    return {
        "intent": intent,
        "mode": "adk",
        "response": {
            "status": "error",
            "mode": "adk",
            "answer": message,
            "tool_trace": [
                trace_item(
                    "Main Coordinator",
                    "Failed before selecting a workflow tool.",
                    message,
                    status="failed",
                )
            ],
        },
    }


def _build_runtime_response(request: ChatRequest, state: dict[str, Any], final_text: str | None) -> dict[str, Any]:
    classified_intent = classify_intent(request.message)
    intent = _public_intent(str(state.get("last_intent") or classified_intent), classified_intent)
    payload = _payload_from_state(state, final_text, request)
    run = _lookup_store_item(store.runs, state.get("last_run_id"))
    report = _lookup_store_item(store.reports, state.get("last_report_id"))
    alert = _lookup_store_item(store.alerts, state.get("last_alert_id"))
    if intent == "REPORT_REQUEST" and report is None:
        report = _attach_missing_report(payload, run, request)
    response: dict[str, Any] = {"intent": intent, "mode": "adk", "response": payload}
    if run is not None:
        response["run"] = run
    if report is not None:
        response["report"] = report
    if alert is not None:
        response["alert"] = alert
    return response


def _payload_from_state(state: dict[str, Any], final_text: str | None, request: ChatRequest) -> dict[str, Any]:
    payload = state.get("last_response_payload")
    if not isinstance(payload, dict):
        return {
            "status": "error",
            "mode": "adk",
            "answer": final_text or "The ADK runtime did not produce a structured response payload.",
        }
    payload = dict(payload)
    payload.setdefault("mode", "adk")
    if payload.get("requires_synthesis"):
        _apply_synthesis_answer(payload, final_text, request)
    return payload


def _attach_missing_report(payload: dict[str, Any], run: RunRecord | None, request: ChatRequest) -> Any | None:
    run_for_report = run or store.get_latest_run(request.region_id)
    report_payload = create_report_for_run(run_for_report)
    if report_payload.get("status") != "success":
        return None
    payload |= report_payload
    return report_payload["report"]


def _apply_synthesis_answer(payload: dict[str, Any], final_text: str | None, request: ChatRequest) -> None:
    if final_text and _valid_synthesis_answer(final_text, payload):
        payload["answer"] = final_text
        payload["synthesis_source"] = "llm"
        return
    payload["answer"] = _safe_synthesis_answer(payload, request)
    payload["synthesis_source"] = "validator"
    trace = payload.setdefault("tool_trace", [])
    trace.append(
        trace_item(
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


def _lookup_store_item(items: dict[str, Any], key: Any) -> Any | None:
    if not key:
        return None
    return items.get(str(key))


def _public_intent(runtime_intent: str, classified_intent: str) -> str:
    if runtime_intent == "ANALYST_QA" and classified_intent != "QUESTION":
        return classified_intent
    return runtime_intent
