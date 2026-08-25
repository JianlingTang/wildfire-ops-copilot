"""ADK Runner/session plumbing: process-wide session service, runner, retries.

Re-exported by app.runtime.adk.__init__ so tests can keep monkeypatching
app.runtime.adk._get_session_service / _get_runner / _ensure_vertex_configuration
by their existing dotted paths.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import google.auth
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.auth.exceptions import DefaultCredentialsError
from google.genai import types

from app.config.settings import settings
from app.models.schemas import ChatRequest
from wildfire_ops_agent.agent import root_agent

APP_NAME = os.getenv("ADK_APP_NAME", "wildfire_ops_agent")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
_SESSION_SERVICE: InMemorySessionService | None = None
_RUNNER: Runner | None = None


def _get_session_service() -> InMemorySessionService:
    global _SESSION_SERVICE
    if _SESSION_SERVICE is None:
        _SESSION_SERVICE = InMemorySessionService()
    return _SESSION_SERVICE


def _get_runner() -> Runner:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = Runner(
            app_name=APP_NAME,
            agent=root_agent,
            session_service=_get_session_service(),
        )
    return _RUNNER


async def _ensure_session(session_service: InMemorySessionService, user_id: str, session_id: str) -> None:
    existing = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    if existing is None:
        await session_service.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id, state={})


async def _merge_request_state(
    session_service: InMemorySessionService,
    user_id: str,
    session_id: str,
    request: ChatRequest,
) -> None:
    session = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    if session is not None:
        session.state.update(_state_delta_for_request(request))


def _state_delta_for_request(request: ChatRequest) -> dict[str, Any]:
    delta: dict[str, Any] = {
        "app:conversation_id": request.conversation_id,
        "app:run_id": request.run_id,
        "app:region_id": request.region_id,
        "app:region_name": request.region_name,
        "app:user_id": request.user_id,
        "app:last_request_message": request.message,
        "last_intent": None,
        "last_response_payload": None,
        "last_run_id": None,
        "last_report_id": None,
        "last_alert_id": None,
        "last_action_id": None,
    }
    if request.aoi and request.aoi.center:
        delta["app:aoi_center"] = list(request.aoi.center)
        delta["app:aoi_radius_km"] = request.aoi.radius_km
    else:
        delta["app:aoi_center"] = None
        delta["app:aoi_radius_km"] = None
    return delta


def _session_id_for(request: ChatRequest) -> str:
    if request.conversation_id:
        return f"conversation:{request.conversation_id}"
    if request.run_id:
        return f"run:{request.run_id}"
    region = request.region_id or settings.demo_region_id
    return f"{request.user_id}:{region}"


def _ensure_vertex_configuration() -> None:
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION")
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is not set for Vertex AI.")
    if not location:
        raise RuntimeError("GOOGLE_CLOUD_LOCATION is not set for Vertex AI.")
    try:
        google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    except DefaultCredentialsError as exc:
        raise RuntimeError(str(exc)) from exc


def _extract_text(content: types.Content | None) -> str | None:
    parts = getattr(content, "parts", None)
    if not content or not parts:
        return None
    chunks: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            chunks.append(text)
    return "\n".join(chunks).strip() or None


def _is_resource_exhausted_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "resource_exhausted" in text or "resource has been exhausted" in text


async def _run_llm_turn_with_retries(run_factory: Any) -> str | None:
    attempts = int(os.getenv("ADK_GEMINI_RETRY_ATTEMPTS", "3"))
    base_delay = float(os.getenv("ADK_GEMINI_RETRY_BASE_DELAY_SECONDS", "1.0"))
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            final_text: str | None = None
            async for event in run_factory():
                if event.is_final_response():
                    text = _extract_text(event.content)
                    if text:
                        final_text = text
            return final_text
        except Exception as exc:
            last_error = exc
            if not _is_resource_exhausted_error(exc) or attempt >= attempts - 1:
                raise
            await asyncio.sleep(base_delay * (2**attempt))
    if last_error:
        raise last_error
    return None
