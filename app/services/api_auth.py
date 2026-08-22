from secrets import compare_digest

from fastapi import HTTPException, Request, WebSocket, status

from app.config.settings import settings

API_AUTH_HEADER = "x-api-key"


def is_api_auth_enabled() -> bool:
    return bool(settings.api_auth_token)


def _is_valid_token(token: str | None) -> bool:
    if not settings.api_auth_token or not token:
        return False
    return compare_digest(token, settings.api_auth_token)


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
    token = request.headers.get(API_AUTH_HEADER) or _bearer_token(request.headers.get("authorization"))
    if not _is_valid_token(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API credentials")


async def verify_api_websocket(websocket: WebSocket) -> bool:
    if not _is_allowed_origin(websocket.headers.get("origin")):
        await websocket.close(code=1008)
        return False
    if not is_api_auth_enabled():
        return True
    token = websocket.query_params.get("api_key") or websocket.headers.get(API_AUTH_HEADER)
    if _is_valid_token(token):
        return True
    await websocket.close(code=1008)
    return False
