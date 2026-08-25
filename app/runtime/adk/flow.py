"""The ADK chat-turn flow: LLM call, then guardrail checks and deterministic
fallbacks. Called from AdkRuntime._route_chat_async (app.runtime.adk.__init__),
kept as free functions since none of them need AdkRuntime instance state."""

from __future__ import annotations

from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.models.schemas import ChatRequest
from app.runtime.adk.dispatch import _route_deterministic_workflow
from app.runtime.adk.guardrails import (
    _missing_action_payload,
    _missing_tool_result,
    _needs_focus_aoi_fallback,
    _should_correct_llm_route,
)
from app.runtime.adk.prompt import _message_with_operational_context
from app.runtime.adk.response import (
    _attach_timing_trace,
    _build_runtime_response,
    _error_response,
    _finalize_chat_response_timed,
    _with_trace_id,
)
from app.runtime.adk.session import (
    APP_NAME,
    _is_resource_exhausted_error,
    _run_llm_turn_with_retries,
    _state_delta_for_request,
)
from app.runtime.intent_responses import publish_chat_event
from app.services.chat_conversations import analysis_required_response
from app.services.timing_trace import TimingTrace

_FALLBACK_INTENTS = {"ACTION_COMMAND", "CALCULATION", "KNOWLEDGE_REQUIRED", "MEMORY_LOOKUP"}


def _publish_intent_events(trace_id: str, request: ChatRequest, conversation: Any, intent: str) -> None:
    publish_chat_event(
        trace_id,
        request,
        conversation.conversation_id,
        "started",
        "Coordinator received chat request.",
        intent,
        mode="adk",
    )
    publish_chat_event(
        trace_id,
        request,
        conversation.conversation_id,
        "completed",
        f"Intent classified: {intent}.",
        intent,
        mode="adk",
    )


def _blocked_for_analysis_response(
    timing: TimingTrace, trace_id: str, request: ChatRequest, conversation: Any, intent: str
) -> dict[str, Any]:
    publish_chat_event(
        trace_id,
        request,
        conversation.conversation_id,
        "blocked",
        "Analysis gate blocked request before workflow tool calls.",
        intent,
        mode="adk",
    )
    response = analysis_required_response(request, conversation, intent, mode="adk", trace_id=trace_id)
    return _attach_timing_trace(response, timing, intent)


def _try_fallback(
    timing: TimingTrace,
    trace_id: str,
    request: ChatRequest,
    conversation: Any,
    intent: str,
    tool_label: str,
    correction_summary: str,
) -> dict[str, Any] | None:
    with timing.step("tool_call", intent=intent, tool=tool_label):
        fallback = _route_deterministic_workflow(request, intent, correction_summary=correction_summary)
    if fallback is None:
        return None
    fallback["trace_id"] = trace_id
    return _finalize_chat_response_timed(request, conversation, fallback, timing)


async def _call_adk_runner(runner: Runner, user_id: str, session_id: str, request: ChatRequest) -> str | None:
    return await _run_llm_turn_with_retries(
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


async def _read_runtime_intent(
    session_service: InMemorySessionService, user_id: str, session_id: str
) -> tuple[str, dict[str, Any]]:
    session = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    session_state = session.state if session else {}
    return str(session_state.get("last_intent") or ""), session_state


async def _run_adk_llm_turn(
    session_service: InMemorySessionService,
    runner: Runner,
    user_id: str,
    session_id: str,
    timing: TimingTrace,
    trace_id: str,
    request: ChatRequest,
    conversation: Any,
    intent: str,
) -> dict[str, Any]:
    with timing.step("adk_llm_call", intent=intent):
        final_text = await _call_adk_runner(runner, user_id, session_id, request)
    with timing.step("adk_session_read", intent=intent):
        runtime_intent, session_state = await _read_runtime_intent(session_service, user_id, session_id)

    if not runtime_intent:
        return _handle_no_tool_called(timing, trace_id, request, conversation, intent)
    if _should_correct_llm_route(intent, runtime_intent):
        corrected = _try_fallback(
            timing,
            trace_id,
            request,
            conversation,
            intent,
            "corrected_deterministic_workflow",
            f"Deterministic guardrail corrected route from {runtime_intent or 'no tool call'} to {intent}.",
        )
        if corrected is not None:
            return corrected

    with timing.step("build_runtime_response", intent=intent, runtime_intent=runtime_intent):
        response = _build_runtime_response(request, session_state, final_text)
    return _finalize_llm_response(timing, trace_id, request, conversation, intent, response)


def _handle_no_tool_called(
    timing: TimingTrace, trace_id: str, request: ChatRequest, conversation: Any, intent: str
) -> dict[str, Any]:
    if intent in _FALLBACK_INTENTS:
        fallback = _try_fallback(
            timing,
            trace_id,
            request,
            conversation,
            intent,
            "action_fallback_no_llm_tool",
            "Deterministic fallback ran because Gemini did not call the required tool.",
        )
        if fallback is not None:
            return fallback
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


def _finalize_llm_response(
    timing: TimingTrace,
    trace_id: str,
    request: ChatRequest,
    conversation: Any,
    intent: str,
    response: dict[str, Any],
) -> dict[str, Any]:
    if intent == "ACTION_COMMAND" and _missing_action_payload(response):
        fallback = _try_fallback(
            timing,
            trace_id,
            request,
            conversation,
            intent,
            "action_fallback_missing_payload",
            "Deterministic fallback ran because Gemini did not return an action approval payload.",
        )
        if fallback is not None:
            return fallback
    if _missing_tool_result(response):
        return _handle_missing_tool_result(timing, trace_id, request, conversation, intent)
    if _needs_focus_aoi_fallback(response, request, intent):
        return _finalize_chat_response_timed(
            request,
            conversation,
            _with_trace_id(
                _error_response(
                    intent, "Gemini/Vertex AI did not answer from the selected AOI context. Retry the question."
                ),
                trace_id,
            ),
            timing,
        )
    response["trace_id"] = trace_id
    return _finalize_chat_response_timed(request, conversation, response, timing)


def _handle_missing_tool_result(
    timing: TimingTrace, trace_id: str, request: ChatRequest, conversation: Any, intent: str
) -> dict[str, Any]:
    if intent in _FALLBACK_INTENTS:
        fallback = _try_fallback(
            timing,
            trace_id,
            request,
            conversation,
            intent,
            "action_fallback_missing_tool_result",
            "Deterministic fallback ran because Gemini did not return a required tool payload.",
        )
        if fallback is not None:
            return fallback
    return _finalize_chat_response_timed(
        request,
        conversation,
        _with_trace_id(
            _error_response(intent, "Gemini/Vertex AI did not produce a structured tool payload or final text."),
            trace_id,
        ),
        timing,
    )


def _handle_runtime_exception(
    timing: TimingTrace,
    trace_id: str,
    request: ChatRequest,
    conversation: Any,
    intent: str,
    exc: Exception,
) -> dict[str, Any]:
    if _is_resource_exhausted_error(exc):
        return _finalize_chat_response_timed(
            request,
            conversation,
            _with_trace_id(_error_response(intent, f"Gemini/Vertex AI runtime failed: {exc}"), trace_id),
            timing,
        )
    if intent in _FALLBACK_INTENTS:
        fallback = _try_fallback(
            timing,
            trace_id,
            request,
            conversation,
            intent,
            "action_safety_fallback",
            f"Safety fallback ran because ADK runtime failed: {exc}",
        )
        if fallback is not None:
            return fallback
    return _finalize_chat_response_timed(
        request,
        conversation,
        _with_trace_id(_error_response(intent, f"ADK runtime failed: {exc}"), trace_id),
        timing,
    )
