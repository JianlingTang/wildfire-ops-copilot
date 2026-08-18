from __future__ import annotations

from typing import Any

from app.config.settings import settings
from app.models.schemas import ChatRequest, ConversationRecord, RunRecord
from app.runtime.intents import classify_intent
from app.services.agent_events import publish_trace_items
from app.services.firestore_store import store

RECENT_MESSAGE_LIMIT = 6


def prepare_conversation(request: ChatRequest) -> tuple[ConversationRecord, ChatRequest]:
    conversation = store.get_or_create_conversation(
        conversation_id=request.conversation_id,
        user_id=request.user_id or "demo_officer",
        region_id=request.region_id or settings.demo_region_id,
        region_name=request.region_name,
        run_id=request.run_id,
    )
    effective_run_id = request.run_id or conversation.run_id
    if effective_run_id != request.run_id or conversation.conversation_id != request.conversation_id:
        request = request.model_copy(
            update={"run_id": effective_run_id, "conversation_id": conversation.conversation_id}
        )
    store.append_chat_message(
        conversation.conversation_id,
        role="user",
        content=request.message,
        intent=classify_intent(request.message),
        run_id=effective_run_id,
        region_id=request.region_id,
    )
    return conversation, request


def completed_run_for_request(request: ChatRequest, conversation: ConversationRecord | None = None) -> RunRecord | None:
    run_id = request.run_id or (conversation.run_id if conversation else None)
    run = store.runs.get(run_id) if run_id else store.get_latest_run(request.region_id)
    if run is None and request.region_id == settings.demo_region_id:
        run = store.get_latest_run()
    if run and run.status == "completed":
        return run
    return None


def should_block_for_analysis(intent: str, request: ChatRequest, conversation: ConversationRecord) -> bool:
    if intent in {"ANALYZE_AND_REPORT", "CALCULATION", "KNOWLEDGE_REQUIRED", "MEMORY_LOOKUP", "QUESTION"}:
        return False
    return completed_run_for_request(request, conversation) is None


def analysis_required_response(
    request: ChatRequest,
    conversation: ConversationRecord,
    intent: str,
    *,
    mode: str,
    trace_id: str | None = None,
) -> dict[str, Any]:
    region_name = request.region_name or conversation.region_name or request.region_id
    trace = [
        {
            "called": "Main Coordinator",
            "did": "Blocked before workflow tool calls.",
            "output": "Analysis required for this AOI.",
            "mode": mode,
            "status": "failed",
        }
    ]
    payload = {
        "status": "must_run_analysis",
        "mode": mode,
        "answer": (
            f"Run analysis first for {region_name}. I need a completed analysis run before questions, "
            "what-if scenarios, visualizations, monitoring, or action drafts for this AOI."
        ),
        "requires_analysis": True,
        "tool_trace": trace,
        "tool_results": {"blocked_reason": "analysis_required", "region_name": region_name},
    }
    response = {"intent": intent, "mode": mode, "response": payload, "requires_analysis": True}
    if trace_id:
        response["trace_id"] = trace_id
    return finalize_chat_response(request, conversation, response)


def finalize_chat_response(
    request: ChatRequest,
    conversation: ConversationRecord,
    response: dict[str, Any],
) -> dict[str, Any]:
    raw_payload = response.get("response")
    payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
    run = response.get("run")
    run_id = _run_id_from_response(response, request, conversation)
    context_run = run if isinstance(run, RunRecord) else (store.runs.get(run_id) if run_id else None)
    region_name = getattr(run, "region_name", None) or request.region_name or conversation.region_name
    context_summary = build_context_summary(conversation, context_run)
    conversation = store.update_conversation_context(
        conversation.conversation_id,
        compressed_context=context_summary,
        run_id=run_id,
        region_name=region_name,
    )
    store.append_chat_message(
        conversation.conversation_id,
        role="assistant",
        content=str(payload.get("answer") or payload.get("message") or "Request completed."),
        intent=str(response.get("intent") or classify_intent(request.message)),
        tool_trace=list(payload.get("tool_trace") or []),
        tool_results=_tool_results_from_payload(payload),
        run_id=run_id,
        region_id=request.region_id,
    )
    trace_id = str(response.get("trace_id") or "")
    if trace_id:
        publish_trace_items(
            trace_id=trace_id,
            tool_trace=list(payload.get("tool_trace") or []),
            conversation_id=conversation.conversation_id,
            run_id=run_id,
            region_id=request.region_id,
        )
    conversation = store.conversations[conversation.conversation_id]
    conversation = store.update_conversation_context(
        conversation.conversation_id,
        compressed_context=build_context_summary(conversation, context_run),
        run_id=run_id,
        region_name=region_name,
    )
    response["conversation_id"] = conversation.conversation_id
    if trace_id:
        response["trace_id"] = trace_id
    response["messages"] = [
        message.model_dump(mode="json") for message in store.get_recent_chat_messages(conversation.conversation_id)
    ]
    response["context_summary"] = conversation.compressed_context
    response.setdefault("requires_analysis", bool(payload.get("requires_analysis")))
    return response


def build_context_summary(conversation: ConversationRecord, run: RunRecord | None = None) -> str:
    older = conversation.messages[:-RECENT_MESSAGE_LIMIT]
    recent = conversation.messages[-RECENT_MESSAGE_LIMIT:]
    parts: list[str] = []
    if conversation.region_name or conversation.region_id:
        parts.append(f"AOI: {conversation.region_name or conversation.region_id}.")
    if run:
        parts.append(f"Latest analysis: {run.region_name} {run.risk_level} {run.risk_score}/100.")
        elastic = run.evidence.get("elastic", {})
        titles = [
            str(item.get("title"))
            for item in elastic.get("evidence", [])[:2]
            if isinstance(item, dict) and item.get("title")
        ]
        if titles:
            parts.append(f"Elastic evidence ({elastic.get('mode', 'unknown')}): {', '.join(titles)}.")
        else:
            parts.append(f"Elastic evidence mode: {elastic.get('mode', 'unknown')}.")
    if older:
        intents = [message.intent for message in older if message.intent]
        if intents:
            parts.append(f"Earlier intents: {', '.join(intents[-6:])}.")
    if recent:
        brief = " | ".join(f"{message.role}: {message.content[:120]}" for message in recent[-4:])
        parts.append(f"Recent conversation: {brief}.")
    return " ".join(parts).strip()


def _run_id_from_response(
    response: dict[str, Any], request: ChatRequest, conversation: ConversationRecord
) -> str | None:
    run = response.get("run")
    if isinstance(run, RunRecord):
        return run.run_id
    payload = response.get("response") if isinstance(response.get("response"), dict) else {}
    tool_run_id = payload.get("run_id") if isinstance(payload, dict) else None
    return str(tool_run_id) if tool_run_id else request.run_id or conversation.run_id


def _tool_results_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    excluded = {"answer", "tool_trace", "mode"}
    results = {key: value for key, value in payload.items() if key not in excluded and key != "tool_results"}
    nested = payload.get("tool_results")
    if isinstance(nested, dict):
        results.update(nested)
    return results
