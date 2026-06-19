from app.models.schemas import Aoi, ChatRequest
from app.services.chat_conversations import (
    analysis_required_response,
    build_context_summary,
    finalize_chat_response,
    prepare_conversation,
    should_block_for_analysis,
)
from app.services.firestore_store import store


def test_conversation_store_appends_and_summarizes_recent_messages() -> None:
    conversation, request = prepare_conversation(ChatRequest(message="Run analysis", region_id="state_nt"))

    for index in range(8):
        store.append_chat_message(
            conversation.conversation_id,
            role="assistant",
            content=f"assistant message {index}",
            intent="QUESTION",
        )

    conversation = store.conversations[conversation.conversation_id]
    summary = build_context_summary(conversation)

    assert len(store.get_recent_chat_messages(conversation.conversation_id)) == 6
    assert "Earlier intents" in summary
    assert request.conversation_id == conversation.conversation_id


def test_analysis_gate_blocks_without_completed_run() -> None:
    conversation, request = prepare_conversation(
        ChatRequest(message="Which area should we inspect first?", region_id="state_nt")
    )

    assert should_block_for_analysis("OPERATIONAL_PRIORITIZATION", request, conversation) is True
    payload = analysis_required_response(request, conversation, "OPERATIONAL_PRIORITIZATION", mode="demo")
    assert payload["response"]["status"] == "must_run_analysis"
    assert payload["response"]["tool_trace"][0]["output"] == "Analysis required for this AOI."


def test_analysis_gate_allows_non_related_question_without_run() -> None:
    conversation, request = prepare_conversation(ChatRequest(message="What is 2 + 2?", region_id="state_nt"))

    assert should_block_for_analysis("QUESTION", request, conversation) is False


def test_analysis_gate_blocks_selected_aoi_without_completed_run() -> None:
    conversation, request = prepare_conversation(
        ChatRequest(
            message="Which area should we inspect first?",
            region_id="state_nt",
            region_name="Northern Territory hotspot cluster focus",
            aoi=Aoi(center=(-11.35, 132.12), radius_km=50),
        )
    )

    assert should_block_for_analysis("OPERATIONAL_PRIORITIZATION", request, conversation) is True


def test_finalize_chat_response_archives_tool_trace_and_results() -> None:
    conversation, request = prepare_conversation(ChatRequest(message="Run analysis", region_id="state_nt"))
    response = finalize_chat_response(
        request,
        conversation,
        {
            "intent": "QUESTION",
            "mode": "demo",
            "response": {
                "status": "success",
                "answer": "Done",
                "tool_trace": [{"called": "Tool", "did": "Worked", "output": "ok"}],
                "tool_results": {"value": 1},
            },
        },
    )

    assistant = response["messages"][-1]
    assert assistant["role"] == "assistant"
    assert assistant["tool_trace"][0]["called"] == "Tool"
    assert assistant["tool_results"]["status"] == "success"
    assert assistant["tool_results"]["value"] == 1
