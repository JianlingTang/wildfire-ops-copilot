"""Per-intent response handlers for the LLM-free demo runtime.

MEMORY_LOOKUP/CALCULATION/KNOWLEDGE_REQUIRED and the exposure/action check are
called directly (they short-circuit before the intent dispatch table, matching
the original if-chain order); everything else is dispatched via
_INTENT_HANDLERS, keyed by classified intent, falling back to
_default_question_handler for the analyst-question family.
"""

from __future__ import annotations

from typing import Any

from app.agents.specialists.analyst_agent import answer_operational_question
from app.agents.specialists.report_agent import create_report_for_run
from app.agents.specialists.what_if_agent import run_what_if
from app.agents.workflows.action_workflow import draft_action
from app.models.schemas import ChatRequest, RunRecord
from app.runtime.intent_responses import knowledge_required_response, publish_artifact_event, trace_for_intent
from app.runtime.mock_demo.analyze import _analyze_and_report
from app.services.chat_conversations import finalize_chat_response
from app.services.conversation_memory import lookup_conversation_memory, memory_operation_for_message
from app.services.deterministic_calculator import calculation_response_from_message
from app.services.hotspot_visualization import build_hotspot_visualization
from app.services.mixed_intents import build_exposure_action_response
from app.services.monitoring_tasks import create_monitor_task_from_chat
from app.services.risk_trend import build_risk_prediction_response, build_risk_trend_response


def _memory_lookup_response(request: ChatRequest, conversation: Any, trace_id: str, intent: str) -> dict[str, Any]:
    operation = memory_operation_for_message(request.message)
    if operation is None:
        payload: dict[str, Any] = {
            "status": "invalid_input",
            "answer": "No supported deterministic memory lookup matched this request.",
            "memory": None,
            "tool_trace": [],
        }
    else:
        payload = lookup_conversation_memory(request, operation)
    payload["mode"] = "demo"
    return finalize_chat_response(
        request, conversation, {"intent": intent, "mode": "demo", "response": payload, "trace_id": trace_id}
    )


def _calculation_response(request: ChatRequest, conversation: Any, trace_id: str, intent: str) -> dict[str, Any]:
    payload = calculation_response_from_message(request.message, mode="demo")
    return finalize_chat_response(
        request, conversation, {"intent": intent, "mode": "demo", "response": payload, "trace_id": trace_id}
    )


def _knowledge_required_response_handler(
    request: ChatRequest, conversation: Any, trace_id: str, intent: str
) -> dict[str, Any]:
    payload = knowledge_required_response(request.message, mode="demo")
    return finalize_chat_response(
        request, conversation, {"intent": intent, "mode": "demo", "response": payload, "trace_id": trace_id}
    )


def _exposure_action_response(
    request: ChatRequest, run: RunRecord | None, conversation: Any, trace_id: str
) -> dict[str, Any]:
    response = build_exposure_action_response(request, run, mode="demo")
    response["trace_id"] = trace_id
    publish_artifact_event(
        trace_id,
        request,
        conversation.conversation_id,
        "approval",
        "Approval requested for mixed exposure/action request.",
        "EXPOSURE_ACTION",
        mode="demo",
    )
    return finalize_chat_response(request, conversation, response)


def _analyze_and_report_handler(
    request: ChatRequest, run: RunRecord | None, conversation: Any, trace_id: str, intent: str
) -> dict[str, Any]:
    publish_artifact_event(
        trace_id, request, conversation.conversation_id, "analysis", "Analysis workflow started.", intent, mode="demo"
    )
    response = _analyze_and_report(request)
    response["trace_id"] = trace_id
    return finalize_chat_response(request, conversation, response)


def _risk_trend_handler(
    request: ChatRequest, run: RunRecord | None, conversation: Any, trace_id: str, intent: str
) -> dict[str, Any]:
    payload = build_risk_trend_response(request, run, mode="demo")
    publish_artifact_event(
        trace_id,
        request,
        conversation.conversation_id,
        "visualization",
        "Risk trend chart generated.",
        intent,
        mode="demo",
    )
    return finalize_chat_response(
        request, conversation, {"intent": intent, "mode": "demo", "response": payload, "trace_id": trace_id}
    )


def _risk_prediction_handler(
    request: ChatRequest, run: RunRecord | None, conversation: Any, trace_id: str, intent: str
) -> dict[str, Any]:
    payload = build_risk_prediction_response(request, run, mode="demo")
    publish_artifact_event(
        trace_id, request, conversation.conversation_id, "risk", "Risk prediction generated.", intent, mode="demo"
    )
    return finalize_chat_response(
        request, conversation, {"intent": intent, "mode": "demo", "response": payload, "trace_id": trace_id}
    )


def _hotspot_visualization_handler(
    request: ChatRequest, run: RunRecord | None, conversation: Any, trace_id: str, intent: str
) -> dict[str, Any]:
    visualization = build_hotspot_visualization(request)
    payload: dict[str, Any] = {
        "status": "success",
        "mode": "demo",
        "answer": (
            f"Generated hotspot heatmap and contour analysis for {visualization['region']['region_name']}. "
            f"{visualization['interpretation']['summary']} The visualization is ready to download."
        ),
        "visualization": visualization,
    }
    payload["tool_trace"] = trace_for_intent(
        intent, payload, region_name=request.region_name or request.region_id, mode="demo"
    )
    response = {"intent": intent, "mode": "demo", "response": payload}
    publish_artifact_event(
        trace_id,
        request,
        conversation.conversation_id,
        "visualization",
        "Hotspot visualization artifact generated.",
        intent,
        mode="demo",
    )
    response["trace_id"] = trace_id
    return finalize_chat_response(request, conversation, response)


def _monitor_task_handler(
    request: ChatRequest, run: RunRecord | None, conversation: Any, trace_id: str, intent: str
) -> dict[str, Any]:
    payload = create_monitor_task_from_chat(request, mode="demo")
    publish_artifact_event(
        trace_id, request, conversation.conversation_id, "monitor", "Monitor task created.", intent, mode="demo"
    )
    return finalize_chat_response(
        request, conversation, {"intent": intent, "mode": "demo", "response": payload, "trace_id": trace_id}
    )


def _what_if_handler(
    request: ChatRequest, run: RunRecord | None, conversation: Any, trace_id: str, intent: str
) -> dict[str, Any]:
    payload = run_what_if(request.message, run, request.region_name, request.aoi)
    payload["tool_trace"] = trace_for_intent(
        intent, payload, region_name=request.region_name or request.region_id, mode="demo"
    )
    return finalize_chat_response(
        request, conversation, {"intent": intent, "mode": "demo", "response": payload, "trace_id": trace_id}
    )


def _action_command_handler(
    request: ChatRequest, run: RunRecord | None, conversation: Any, trace_id: str, intent: str
) -> dict[str, Any]:
    payload = draft_action(request.message, run, request.user_id, request.region_name)
    payload["tool_trace"] = trace_for_intent(
        intent, payload, region_name=request.region_name or request.region_id, mode="demo"
    )
    publish_artifact_event(
        trace_id,
        request,
        conversation.conversation_id,
        "approval",
        "Approval requested for drafted action.",
        intent,
        mode="demo",
    )
    return finalize_chat_response(
        request, conversation, {"intent": intent, "mode": "demo", "response": payload, "trace_id": trace_id}
    )


def _report_request_handler(
    request: ChatRequest, run: RunRecord | None, conversation: Any, trace_id: str, intent: str
) -> dict[str, Any]:
    result = create_report_for_run(run)
    result["tool_trace"] = trace_for_intent(intent, result, region_name=None, mode="demo")
    if result.get("status") == "success":
        result["answer"] = "Generated a fresh operations brief from the latest completed run in demo mode."
        return finalize_chat_response(
            request,
            conversation,
            {"intent": intent, "mode": "demo", "response": result, "report": result["report"], "trace_id": trace_id},
        )
    return finalize_chat_response(
        request, conversation, {"intent": intent, "mode": "demo", "response": result, "trace_id": trace_id}
    )


def _default_question_handler(
    request: ChatRequest, run: RunRecord | None, conversation: Any, trace_id: str, intent: str
) -> dict[str, Any]:
    payload = answer_operational_question(request.message, run, request.region_name, request.aoi)
    payload["tool_trace"] = trace_for_intent(
        intent, payload, region_name=request.region_name or request.region_id, mode="demo"
    )
    return finalize_chat_response(
        request, conversation, {"intent": intent, "mode": "demo", "response": payload, "trace_id": trace_id}
    )


_INTENT_HANDLERS = {
    "ANALYZE_AND_REPORT": _analyze_and_report_handler,
    "RISK_TREND": _risk_trend_handler,
    "RISK_PREDICTION": _risk_prediction_handler,
    "HOTSPOT_VISUALIZATION": _hotspot_visualization_handler,
    "MONITOR_TASK": _monitor_task_handler,
    "WHAT_IF": _what_if_handler,
    "ACTION_COMMAND": _action_command_handler,
    "REPORT_REQUEST": _report_request_handler,
}
