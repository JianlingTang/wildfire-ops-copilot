from datetime import UTC, datetime

import pytest

from app.models.schemas import Aoi, ChatRequest
from app.services.conversation_memory import lookup_conversation_memory
from app.services.firestore_store import store


@pytest.fixture(autouse=True)
def reset_store() -> None:
    store.reset()


def _conversation(*, user_id: str = "eval_user", run_id: str | None = None):
    return store.get_or_create_conversation(
        conversation_id="conv_memory",
        user_id=user_id,
        region_id="blue_mountains",
        region_name="Blue Mountains",
        run_id=run_id,
    )


def _completed_run():
    run = store.create_run("blue_mountains", "Blue Mountains")
    return store.complete_run(
        run.run_id,
        evidence={
            "region_context": {
                "region_id": "blue_mountains",
                "region_name": "Blue Mountains",
                "center": [-33.71, 150.31],
                "radius_km": 25.0,
            }
        },
        risk_assessment={"risk_score": 72, "risk_level": "HIGH"},
        recommendations=["Continue monitoring."],
    )


def test_last_user_question_returns_exact_previous_message() -> None:
    conversation = _conversation()
    store.append_chat_message(conversation.conversation_id, role="user", content="How many hotspots are active?")
    store.append_chat_message(conversation.conversation_id, role="assistant", content="There are three.")
    store.append_chat_message(conversation.conversation_id, role="user", content="What was my last question?")

    result = lookup_conversation_memory(
        ChatRequest(
            message="What was my last question?",
            conversation_id=conversation.conversation_id,
            user_id="eval_user",
        ),
        "LAST_USER_QUESTION",
    )

    assert result["status"] == "success"
    assert result["memory"]["value"] == "How many hotspots are active?"
    assert result["memory"]["source"] == "conversation.messages"


def test_last_user_question_skips_only_the_current_duplicate() -> None:
    conversation = _conversation()
    store.append_chat_message(conversation.conversation_id, role="user", content="What was my last question?")
    store.append_chat_message(conversation.conversation_id, role="assistant", content="No earlier question was found.")
    store.append_chat_message(conversation.conversation_id, role="user", content="What was my last question?")

    result = lookup_conversation_memory(
        ChatRequest(
            message="What was my last question?",
            conversation_id=conversation.conversation_id,
            user_id="eval_user",
        ),
        "LAST_USER_QUESTION",
    )

    assert result["memory"]["value"] == "What was my last question?"


def test_last_user_question_returns_not_found_without_previous_message() -> None:
    conversation = _conversation()
    store.append_chat_message(conversation.conversation_id, role="user", content="What was my last question?")

    result = lookup_conversation_memory(
        ChatRequest(
            message="What was my last question?",
            conversation_id=conversation.conversation_id,
            user_id="eval_user",
        ),
        "LAST_USER_QUESTION",
    )

    assert result["status"] == "not_found"
    assert result["memory"] is None


def test_memory_lookup_rejects_cross_user_conversation_access() -> None:
    conversation = _conversation(user_id="owner")
    store.append_chat_message(conversation.conversation_id, role="user", content="Private operational question")

    result = lookup_conversation_memory(
        ChatRequest(
            message="What was my last question?",
            conversation_id=conversation.conversation_id,
            user_id="other_user",
        ),
        "LAST_USER_QUESTION",
    )

    assert result["status"] == "forbidden"
    assert result["memory"] is None


def test_active_aoi_prefers_explicit_structured_request() -> None:
    conversation = _conversation()
    request = ChatRequest(
        message="What is my selected AOI?",
        conversation_id=conversation.conversation_id,
        user_id="eval_user",
        region_id="custom_aoi",
        region_name="Katoomba West",
        aoi=Aoi(center=(-33.72, 150.29), radius_km=12.5),
    )

    result = lookup_conversation_memory(request, "ACTIVE_AOI")

    assert result["status"] == "success"
    assert result["memory"]["value"] == {
        "region_id": "custom_aoi",
        "region_name": "Katoomba West",
        "center": [-33.72, 150.29],
        "radius_km": 12.5,
        "bbox": None,
    }
    assert result["memory"]["source"] == "request.aoi"


def test_latest_report_aoi_joins_report_to_run_evidence() -> None:
    run = _completed_run()
    conversation = _conversation(run_id=run.run_id)
    report = store.create_report(
        {
            "run_id": run.run_id,
            "type": "situation_report",
            "title": "Blue Mountains Situation Report",
            "markdown": "Evidence-backed report.",
        }
    )

    result = lookup_conversation_memory(
        ChatRequest(
            message="What was my report AOI?",
            conversation_id=conversation.conversation_id,
            run_id=run.run_id,
            user_id="eval_user",
        ),
        "LATEST_REPORT_AOI",
    )

    assert result["status"] == "success"
    assert result["memory"]["report_id"] == report.report_id
    assert result["memory"]["run_id"] == run.run_id
    assert result["memory"]["value"]["center"] == [-33.71, 150.31]
    assert result["memory"]["source"] == "report.run.evidence.region_context"


def test_latest_report_aoi_does_not_claim_missing_report() -> None:
    run = _completed_run()
    conversation = _conversation(run_id=run.run_id)

    result = lookup_conversation_memory(
        ChatRequest(
            message="What was my report AOI?",
            conversation_id=conversation.conversation_id,
            run_id=run.run_id,
            user_id="eval_user",
        ),
        "LATEST_REPORT_AOI",
    )

    assert result["status"] == "not_found"
    assert result["memory"] is None
    assert "report" in result["answer"].lower()


def test_last_action_status_returns_persisted_state() -> None:
    run = _completed_run()
    conversation = _conversation(run_id=run.run_id)
    action, approval = store.create_action(
        {
            "run_id": run.run_id,
            "alert_id": None,
            "action_type": "public_advisory",
            "title": "Draft public advisory",
            "draft": "Prepare for worsening conditions.",
            "requested_by": "eval_user",
        }
    )

    result = lookup_conversation_memory(
        ChatRequest(
            message="What is the status of my last action?",
            conversation_id=conversation.conversation_id,
            run_id=run.run_id,
            user_id="eval_user",
        ),
        "LAST_ACTION_STATUS",
    )

    assert result["status"] == "success"
    assert result["memory"]["value"] == "pending_approval"
    assert result["memory"]["action_id"] == action.action_id
    assert result["memory"]["approval_id"] == approval.approval_id
    assert result["memory"]["source"] == "actions"
