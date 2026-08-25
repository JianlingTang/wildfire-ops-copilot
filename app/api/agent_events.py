from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.agent_events import hub, recent_agent_events
from app.services.api_auth import verify_api_websocket

router = APIRouter(tags=["agent-events"])

# Kept apart from `router` because app.main applies an HTTP-only dependency to that one,
# and FastAPI cannot build a Request from a WebSocket scope. This route authenticates
# itself instead.
websocket_router = APIRouter(tags=["agent-events"])


@router.get("/agent-events/recent")
def get_recent_agent_events(limit: int = 20) -> dict:
    return {"events": recent_agent_events(limit)}


@websocket_router.websocket("/agent-events/ws")
async def agent_events_ws(websocket: WebSocket) -> None:
    if not await verify_api_websocket(websocket):
        return
    hub.register(websocket)
    # Tells the client the socket is authenticated and live, rather than about to close.
    await websocket.send_json({"type": "ready"})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(websocket)
