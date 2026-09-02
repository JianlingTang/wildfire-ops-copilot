"""Google ADK + Gemini chat runtime: LLM tool-calling with a deterministic fallback.

Package layout:
- session.py: ADK Runner/session-service plumbing and Gemini retry loop.
- prompt.py: operator-context prompt construction for the LLM turn.
- dispatch.py: deterministic (non-LLM) per-intent workflow handlers, used both
  as the fallback path and to run ANALYZE_AND_REPORT/HOTSPOT_VISUALIZATION.
- guardrails.py: predicates that decide whether the LLM's tool choice/response
  needs a deterministic correction.
- response.py: turns ADK session state into the final response shape and
  validates the LLM's final text against deterministic synthesis.
- synthesis.py: the LLM-free operator-answer synthesis used by response.py
  when the LLM's text is missing or off-target.
- flow.py: the chat-turn flow that ties the above together (LLM call, then
  guardrail checks and fallbacks).

This module (AdkRuntime) is what tests monkeypatch by dotted path (e.g.
app.runtime.adk._get_session_service), so the ADK plumbing functions are
re-exported here rather than accessed only via qualified submodule paths.
"""

from __future__ import annotations

import asyncio

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from app.agents.workflows.daily_intelligence import run_daily_intelligence
from app.config.settings import settings
from app.models.schemas import ChatRequest, ManualRunRequest
from app.runtime.adk.flow import (
    _blocked_for_analysis_response,
    _handle_runtime_exception,
    _publish_intent_events,
    _run_adk_llm_turn,
)
from app.runtime.adk.prompt import _message_with_operational_context
from app.runtime.adk.response import _attach_timing_trace, _public_intent
from app.runtime.adk.session import (
    _ensure_session,
    _ensure_vertex_configuration,
    _get_runner,
    _get_session_service,
    _merge_request_state,
    _session_id_for,
    _state_delta_for_request,
)
from app.runtime.base import AgentRuntime
from app.runtime.intent_responses import publish_chat_event
from app.runtime.intents import classify_intent
from app.services.agent_events import new_trace_id
from app.services.chat_conversations import prepare_conversation, should_block_for_analysis
from app.services.request_scope import is_wildfire_operations_request, out_of_scope_response
from app.services.timing_trace import TimingTrace

__all__ = ["AdkRuntime", "_message_with_operational_context", "_public_intent"]


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
        _publish_intent_events(trace_id, request, conversation, intent)
        with timing.step("analysis_gate", intent=intent):
            blocked_for_analysis = should_block_for_analysis(intent, request, conversation)
        if blocked_for_analysis:
            return _blocked_for_analysis_response(timing, trace_id, request, conversation, intent)
        publish_chat_event(
            trace_id, request, conversation.conversation_id, "completed", "Analysis gate passed.", intent, mode="adk"
        )
        try:
            with timing.step("adk_setup", intent=intent):
                session_service, runner, user_id, session_id = await _prepare_adk_session(request)
            return await _run_adk_llm_turn(
                session_service, runner, user_id, session_id, timing, trace_id, request, conversation, intent
            )
        except Exception as exc:
            return _handle_runtime_exception(timing, trace_id, request, conversation, intent, exc)


async def _prepare_adk_session(request: ChatRequest) -> tuple[InMemorySessionService, Runner, str, str]:
    _ensure_vertex_configuration()
    session_service = _get_session_service()
    runner = _get_runner()
    user_id = request.user_id or "demo_officer"
    session_id = _session_id_for(request)
    await _ensure_session(session_service, user_id, session_id, _state_delta_for_request(request))
    await _merge_request_state(session_service, user_id, session_id, request)
    return session_service, runner, user_id, session_id
