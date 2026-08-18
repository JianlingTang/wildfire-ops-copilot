from __future__ import annotations

from typing import Any, Literal, cast

from app.models.schemas import ChatRequest, ConversationRecord, RunRecord
from app.services.firestore_store import store

MemoryOperation = Literal[
    "LAST_USER_QUESTION",
    "ACTIVE_AOI",
    "LATEST_REPORT_AOI",
    "LAST_ACTION_STATUS",
]


def memory_operation_for_message(message: str) -> MemoryOperation | None:
    """Map a small, explicit set of state questions to deterministic lookups."""
    normalized = " ".join(message.lower().split())
    if any(
        phrase in normalized
        for phrase in (
            "my last question",
            "my previous question",
            "what did i ask",
            "what was i asking",
        )
    ):
        return "LAST_USER_QUESTION"
    if (
        "report" in normalized
        and any(term in normalized for term in ("aoi", "area", "region"))
        and any(term in normalized for term in ("my", "last", "previous", "what", "which"))
    ):
        return "LATEST_REPORT_AOI"
    if any(term in normalized for term in ("action", "advisory", "draft")) and any(
        term in normalized for term in ("status", "state", "approved", "pending")
    ):
        return "LAST_ACTION_STATUS"
    if any(
        phrase in normalized
        for phrase in (
            "my selected aoi",
            "my current aoi",
            "selected area",
            "current area",
            "active aoi",
        )
    ):
        return "ACTIVE_AOI"
    return None


def lookup_conversation_memory(request: ChatRequest, operation: MemoryOperation) -> dict[str, Any]:
    """Read exact conversation/business state without model inference or generation."""
    conversation = store.conversations.get(request.conversation_id or "")
    if conversation is None:
        return _result(
            operation,
            status="not_found",
            answer="No matching in-memory conversation was found.",
        )
    if conversation.user_id != request.user_id:
        return _result(
            operation,
            status="forbidden",
            answer="This conversation is not available to the current user.",
        )

    if operation == "LAST_USER_QUESTION":
        return _last_user_question(request, conversation)
    if operation == "ACTIVE_AOI":
        return _active_aoi(request, conversation)
    if operation == "LATEST_REPORT_AOI":
        return _latest_report_aoi(request, conversation)
    if operation == "LAST_ACTION_STATUS":
        return _last_action_status(request, conversation)
    raise ValueError(f"Unsupported memory operation: {operation}")


def _last_user_question(request: ChatRequest, conversation: ConversationRecord) -> dict[str, Any]:
    user_messages = [message for message in conversation.messages if message.role == "user"]
    if user_messages and user_messages[-1].content == request.message:
        user_messages = user_messages[:-1]
    if not user_messages:
        return _result(
            "LAST_USER_QUESTION",
            status="not_found",
            answer="No earlier user question was found in this conversation.",
        )
    message = user_messages[-1]
    memory = {
        "value": message.content,
        "message_id": message.message_id,
        "created_at": message.created_at.isoformat(),
        "source": "conversation.messages",
    }
    return _result(
        "LAST_USER_QUESTION",
        status="success",
        answer=f'Your previous question was: "{message.content}"',
        memory=memory,
    )


def _active_aoi(request: ChatRequest, conversation: ConversationRecord) -> dict[str, Any]:
    if request.aoi is not None:
        memory = {
            "value": {
                "region_id": request.region_id,
                "region_name": request.region_name or conversation.region_name or request.region_id,
                "center": list(request.aoi.center) if request.aoi.center else None,
                "radius_km": request.aoi.radius_km,
                "bbox": request.aoi.bbox,
            },
            "source": "request.aoi",
        }
        return _result(
            "ACTIVE_AOI",
            status="success",
            answer=_aoi_answer(cast(dict[str, Any], memory["value"])),
            memory=memory,
        )

    run = _run_for_request(request, conversation)
    region_context = run.evidence.get("region_context") if run else None
    if isinstance(region_context, dict):
        value = _normalized_region_context(region_context, run)
        return _result(
            "ACTIVE_AOI",
            status="success",
            answer=_aoi_answer(value),
            memory={"value": value, "run_id": run.run_id, "source": "run.evidence.region_context"},
        )

    if conversation.region_id:
        value = {
            "region_id": conversation.region_id,
            "region_name": conversation.region_name or conversation.region_id,
            "center": None,
            "radius_km": None,
            "bbox": None,
        }
        return _result(
            "ACTIVE_AOI",
            status="success",
            answer=_aoi_answer(value),
            memory={"value": value, "source": "conversation"},
        )
    return _result("ACTIVE_AOI", status="not_found", answer="No active AOI was found.")


def _latest_report_aoi(request: ChatRequest, conversation: ConversationRecord) -> dict[str, Any]:
    run = _run_for_request(request, conversation)
    if run is None:
        return _result(
            "LATEST_REPORT_AOI",
            status="not_found",
            answer="No completed run was found for a report AOI lookup.",
        )
    reports = [report for report in store.reports.values() if report.run_id == run.run_id]
    if not reports:
        return _result(
            "LATEST_REPORT_AOI",
            status="not_found",
            answer="No persisted report was found for the selected analysis run.",
        )
    report = max(reports, key=lambda item: item.created_at)
    region_context = run.evidence.get("region_context")
    if not isinstance(region_context, dict):
        return _result(
            "LATEST_REPORT_AOI",
            status="not_found",
            answer="The persisted report has no structured AOI evidence.",
        )
    value = _normalized_region_context(region_context, run)
    return _result(
        "LATEST_REPORT_AOI",
        status="success",
        answer=f"The AOI for {report.title} is {_aoi_text(value)}.",
        memory={
            "value": value,
            "report_id": report.report_id,
            "run_id": run.run_id,
            "source": "report.run.evidence.region_context",
        },
    )


def _last_action_status(request: ChatRequest, conversation: ConversationRecord) -> dict[str, Any]:
    effective_run_id = request.run_id or conversation.run_id
    actions = [
        action
        for action in store.actions.values()
        if action.requested_by == request.user_id
        and (effective_run_id is None or action.run_id == effective_run_id)
    ]
    if not actions:
        return _result(
            "LAST_ACTION_STATUS",
            status="not_found",
            answer="No persisted action was found for the current user and analysis run.",
        )
    action = max(actions, key=lambda item: item.created_at)
    approval = next(
        (item for item in store.approvals.values() if item.action_id == action.action_id),
        None,
    )
    memory = {
        "value": action.status,
        "action_id": action.action_id,
        "approval_id": approval.approval_id if approval else None,
        "action_type": action.action_type,
        "title": action.title,
        "source": "actions",
    }
    return _result(
        "LAST_ACTION_STATUS",
        status="success",
        answer=f'The latest action "{action.title}" is {action.status}.',
        memory=memory,
    )


def _run_for_request(request: ChatRequest, conversation: ConversationRecord) -> RunRecord | None:
    run_id = request.run_id or conversation.run_id
    return store.runs.get(run_id) if run_id else None


def _normalized_region_context(region_context: dict[str, Any], run: RunRecord) -> dict[str, Any]:
    center = region_context.get("center")
    return {
        "region_id": str(region_context.get("region_id") or run.region_id),
        "region_name": str(region_context.get("region_name") or run.region_name),
        "center": list(center) if isinstance(center, (list, tuple)) else None,
        "radius_km": region_context.get("radius_km"),
        "bbox": region_context.get("bbox"),
    }


def _aoi_answer(value: dict[str, Any]) -> str:
    return f"The active AOI is {_aoi_text(value)}."


def _aoi_text(value: dict[str, Any]) -> str:
    label = str(value.get("region_name") or value.get("region_id") or "the selected area")
    center = value.get("center")
    radius = value.get("radius_km")
    if isinstance(center, list) and len(center) == 2 and radius is not None:
        return f"{label}, centered at {center[0]}, {center[1]} with a {radius} km radius"
    return label


def _result(
    operation: MemoryOperation,
    *,
    status: Literal["success", "not_found", "forbidden"],
    answer: str,
    memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "answer": answer,
        "operation": operation,
        "memory": memory,
        "requires_synthesis": False,
        "tool_trace": [
            {
                "called": "Conversation Memory Tool",
                "did": f"Performed deterministic {operation} lookup.",
                "output": status,
            }
        ],
        "tool_results": {"memory": memory, "operation": operation, "status": status},
    }
