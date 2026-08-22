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


def test_client_supplied_conversation_id_is_never_adopted() -> None:
    conversation = store.get_or_create_conversation(
        conversation_id="pending",
        user_id="officer_a",
        region_id="state_nsw",
    )

    assert conversation.conversation_id != "pending"
    assert conversation.conversation_id.startswith("conv_")
    assert "pending" not in store.conversations


def test_two_users_sending_the_same_id_do_not_share_a_conversation() -> None:
    first = store.get_or_create_conversation(
        conversation_id="pending", user_id="officer_a", region_id="state_nsw"
    )
    second = store.get_or_create_conversation(
        conversation_id="pending", user_id="officer_b", region_id="state_nsw"
    )

    assert first.conversation_id != second.conversation_id
    assert second.user_id == "officer_b"


def test_owner_resumes_their_own_conversation() -> None:
    first = store.get_or_create_conversation(
        conversation_id=None, user_id="officer_a", region_id="state_nsw"
    )
    resumed = store.get_or_create_conversation(
        conversation_id=first.conversation_id, user_id="officer_a", region_id="state_nsw"
    )

    assert resumed.conversation_id == first.conversation_id


def test_non_owner_cannot_join_an_existing_conversation() -> None:
    owned = store.get_or_create_conversation(
        conversation_id=None, user_id="officer_a", region_id="state_nsw"
    )
    store.append_chat_message(owned.conversation_id, role="user", content="A private question")

    intruder = store.get_or_create_conversation(
        conversation_id=owned.conversation_id, user_id="officer_b", region_id="state_nsw"
    )

    assert intruder.conversation_id != owned.conversation_id
    assert intruder.messages == []
    assert store.conversations[owned.conversation_id].user_id == "officer_a"
