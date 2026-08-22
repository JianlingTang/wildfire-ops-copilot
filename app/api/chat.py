import json

from fastapi import APIRouter, Request

from app.agents.root_agent import route_chat
from app.models.schemas import ChatRequest
from app.services.api_auth import authenticated_actor
from app.services.timing_trace import TimingTrace

router = APIRouter(tags=["chat"])


@router.post("/chat")
def chat(request: Request, payload: ChatRequest) -> dict:
    payload = payload.model_copy(update={"user_id": authenticated_actor(request, payload.user_id)})
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
