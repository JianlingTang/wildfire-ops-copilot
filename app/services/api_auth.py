from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, WebSocket, status
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token

from app.config.settings import settings


@dataclass(frozen=True)
class AuthUser:
    uid: str
    email: str
    role: str


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
    user = _verified_auth_user(token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API credentials")
    if not _is_allowed_user(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not authorized for this app")
    request.state.auth_user = user


async def verify_api_websocket(websocket: WebSocket) -> bool:
    if not _is_allowed_origin(websocket.headers.get("origin")):
        await websocket.close(code=1008)
        return False
    if not is_api_auth_enabled():
        return True
    token = websocket.query_params.get("id_token")
    user = _verified_auth_user(token)
    if user is not None and _is_allowed_user(user):
        return True
    await websocket.close(code=1008)
    return False


def get_authenticated_user(request: Request) -> AuthUser | None:
    user = getattr(request.state, "auth_user", None)
    return user if isinstance(user, AuthUser) else None


def authenticated_actor(request: Request, fallback: str) -> str:
    """Resolve who is acting, from the verified token rather than the request body.

    Identity keys conversation ownership, an action's requested_by, and the audit log,
    so a caller that could set it could read another operator's transcript or act in
    their name. The fallback is only honoured when auth is switched off for local
    development. Returns the email so every actor recorded across the app is the same
    kind of identifier and can be compared.
    """
    if not is_api_auth_enabled():
        return fallback
    user = get_authenticated_user(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authenticated user is required")
    return user.email


def require_admin_user(request: Request) -> AuthUser:
    user = get_authenticated_user(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role is required")
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role is required")
    return user


def _verified_auth_user(token: str | None) -> AuthUser | None:
    if not settings.firebase_project_id or not token:
        return None
    try:
        claims = id_token.verify_firebase_token(
            token,
            google_auth_requests.Request(),
            audience=settings.firebase_project_id,
        )
    except (ValueError, google_auth_exceptions.GoogleAuthError):
        return None
    return _auth_user_from_claims(claims)


def _auth_user_from_claims(claims: dict[str, Any]) -> AuthUser | None:
    email = str(claims.get("email", "")).strip().lower()
    if not email:
        return None
    if settings.auth_require_verified_email and claims.get("email_verified") is not True:
        return None
    uid = str(claims.get("user_id") or claims.get("sub") or "").strip()
    if not uid:
        return None
    role = "admin" if email in settings.auth_admin_emails else "operator"
    return AuthUser(uid=uid, email=email, role=role)


def _is_allowed_user(user: AuthUser) -> bool:
    allowed_emails = {*settings.auth_allowed_emails, *settings.auth_admin_emails}
    return bool(allowed_emails) and user.email in allowed_emails
