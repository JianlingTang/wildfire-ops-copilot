from fastapi import HTTPException, Request, WebSocket, status
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token

from app.config.settings import settings


def is_api_auth_enabled() -> bool:
    return bool(settings.firebase_project_id)


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _is_allowed_origin(origin: str | None) -> bool:
    if not origin:
        return True
    allowed_origins = {configured.rstrip("/") for configured in settings.cors_origins}
    return origin.rstrip("/") in allowed_origins


def verify_api_request(request: Request) -> None:
    if not is_api_auth_enabled():
        return
    token = _bearer_token(request.headers.get("authorization"))
    if not _is_valid_firebase_token(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API credentials")


async def verify_api_websocket(websocket: WebSocket) -> bool:
    if not _is_allowed_origin(websocket.headers.get("origin")):
        await websocket.close(code=1008)
        return False
    if not is_api_auth_enabled():
        return True
    token = websocket.query_params.get("id_token")
    if _is_valid_firebase_token(token):
        return True
    await websocket.close(code=1008)
    return False


def _is_valid_firebase_token(token: str | None) -> bool:
    if not settings.firebase_project_id or not token:
        return False
    try:
        id_token.verify_firebase_token(
            token,
            google_auth_requests.Request(),
            audience=settings.firebase_project_id,
        )
    except (ValueError, google_auth_exceptions.GoogleAuthError):
        return False
    return True
