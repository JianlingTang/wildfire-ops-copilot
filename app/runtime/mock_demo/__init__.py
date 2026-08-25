"""LLM-free demo chat runtime: deterministic per-intent handlers, no Gemini/ADK calls.

Package layout:
- handlers.py: one function per intent (plus the dispatch table), and the
  three checks (MEMORY_LOOKUP/CALCULATION/KNOWLEDGE_REQUIRED/exposure-action)
  that short-circuit before it, in the same order as the original if-chain.
- analyze.py: the ANALYZE_AND_REPORT handler, which runs the shared analysis
  pipeline rather than a lightweight per-intent lookup.
"""

from __future__ import annotations

from typing import Any

from app.agents.workflows.daily_intelligence import run_daily_intelligence
from app.config.settings import settings
from app.models.schemas import ChatRequest, ManualRunRequest, RunRecord
from app.runtime.base import AgentRuntime
from app.runtime.intent_responses import publish_chat_event
from app.runtime.intents import classify_intent
from app.runtime.mock_demo.handlers import (
    _INTENT_HANDLERS,
    _calculation_response,
    _default_question_handler,
    _exposure_action_response,
    _knowledge_required_response_handler,
    _memory_lookup_response,
)
from app.services.agent_events import new_trace_id
from app.services.chat_conversations import (
    analysis_required_response,
    prepare_conversation,
    should_block_for_analysis,
)
from app.services.firestore_store import store
from app.services.mixed_intents import is_exposure_action_request
from app.services.request_scope import is_wildfire_operations_request, out_of_scope_response

__all__ = ["MockDemoRuntime"]


class MockDemoRuntime(AgentRuntime):
    def run_daily(self) -> dict:
        request = ManualRunRequest(region_id=settings.demo_region_id, region_name=settings.demo_region_name)
        return run_daily_intelligence(request, trigger_type="daily")

    def run_manual(self, request: ManualRunRequest) -> dict:
        return run_daily_intelligence(request, trigger_type="manual")

    def route_chat(self, request: ChatRequest) -> dict:
        if not is_wildfire_operations_request(request):
            return out_of_scope_response(mode="demo")
        conversation, request = prepare_conversation(request)
        trace_id = new_trace_id()
        intent = classify_intent(request.message)
        _publish_intent_events(trace_id, request, conversation, intent)
        if should_block_for_analysis(intent, request, conversation):
            publish_chat_event(
                trace_id,
                request,
                conversation.conversation_id,
                "blocked",
                "Analysis gate blocked request before workflow tool calls.",
                intent,
                mode="demo",
            )
            return analysis_required_response(request, conversation, intent, mode="demo", trace_id=trace_id)
        publish_chat_event(
            trace_id, request, conversation.conversation_id, "completed", "Analysis gate passed.", intent, mode="demo"
        )

        run = _resolve_run(request)
        if intent == "MEMORY_LOOKUP":
            return _memory_lookup_response(request, conversation, trace_id, intent)
        if intent == "CALCULATION":
            return _calculation_response(request, conversation, trace_id, intent)
        if intent == "KNOWLEDGE_REQUIRED":
            return _knowledge_required_response_handler(request, conversation, trace_id, intent)
        if is_exposure_action_request(request.message):
            return _exposure_action_response(request, run, conversation, trace_id)
        handler = _INTENT_HANDLERS.get(intent, _default_question_handler)
        return handler(request, run, conversation, trace_id, intent)


def _publish_intent_events(trace_id: str, request: ChatRequest, conversation: Any, intent: str) -> None:
    publish_chat_event(
        trace_id,
        request,
        conversation.conversation_id,
        "started",
        "Coordinator received chat request.",
        intent,
        mode="demo",
    )
    publish_chat_event(
        trace_id,
        request,
        conversation.conversation_id,
        "completed",
        f"Intent classified: {intent}.",
        intent,
        mode="demo",
    )


def _resolve_run(request: ChatRequest) -> RunRecord | None:
    run = store.runs.get(request.run_id) if request.run_id else store.get_latest_run(request.region_id)
    if run is None and request.region_id == settings.demo_region_id:
        run = store.get_latest_run()
    return run
