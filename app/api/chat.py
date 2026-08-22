import json

from fastapi import APIRouter, HTTPException, Request, status

from app.agents.root_agent import route_chat
from app.models.schemas import ChatRequest
from app.services.api_auth import get_authenticated_user, is_api_auth_enabled
from app.services.timing_trace import TimingTrace

router = APIRouter(tags=["chat"])


@router.post("/chat")
def chat(request: Request, payload: ChatRequest) -> dict:
    payload = payload.model_copy(update={"user_id": _chat_user_id(request, payload)})
    timing = TimingTrace()
    with timing.step("api_route_chat"):
        response = route_chat(payload)
    trace = response.get("timing_trace") if isinstance(response, dict) else None
    if isinstance(trace, dict):
        trace.setdefault("steps", []).append(timing.snapshot()["steps"][0])
        trace["api_total_ms"] = timing.snapshot()["total_ms"]
    elif isinstance(response, dict):
        response["timing_trace"] = timing.snapshot()
    if isinstance(response, dict):
        print(
            json.dumps(
                {"event": "chat_timing", "trace_id": response.get("trace_id"), "timing": response.get("timing_trace")},
                default=str,
            )
        )
    return response


def _chat_user_id(request: Request, payload: ChatRequest) -> str:
    """Identity comes from the verified token, never from the request body.

    Conversation ownership and an action's requested_by are both keyed on this value,
    so a caller that could set it could read another operator's transcript or file an
    action in their name. Returning the email keeps it comparable with the approval
    actor, which app.api.actions resolves the same way.
    """
    if not is_api_auth_enabled():
        return payload.user_id
    user = get_authenticated_user(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authenticated user is required")
    return user.email
