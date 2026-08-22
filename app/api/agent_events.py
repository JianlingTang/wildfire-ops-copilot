from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.agent_events import hub, recent_agent_events
from app.services.api_auth import verify_api_websocket

router = APIRouter(tags=["agent-events"])


@router.get("/agent-events/recent")
def get_recent_agent_events(limit: int = 20) -> dict:
    return {"events": recent_agent_events(limit)}


@router.websocket("/agent-events/ws")
async def agent_events_ws(websocket: WebSocket) -> None:
    if not await verify_api_websocket(websocket):
        return
    await hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(websocket)
