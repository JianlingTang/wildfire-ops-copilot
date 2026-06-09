from fastapi import APIRouter

from app.agents.root_agent import route_chat
from app.models.schemas import ChatRequest

router = APIRouter(tags=["chat"])


@router.post("/chat")
def chat(request: ChatRequest) -> dict:
    return route_chat(request)
