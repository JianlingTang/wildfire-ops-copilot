"""Predicates that decide whether the LLM's tool choice/response needs a
deterministic correction (see app.runtime.adk.flow)."""

from __future__ import annotations

from typing import Any

from app.models.schemas import ChatRequest
from app.runtime.adk.dispatch import ANALYST_SYNTHESIS_INTENTS


def _should_correct_llm_route(classified_intent: str, runtime_intent: str) -> bool:
    if classified_intent == "ACTION_COMMAND":
        return runtime_intent not in {
            "ACTION_COMMAND",
            "EXPOSURE_ACTION",
        }
    return classified_intent in ANALYST_SYNTHESIS_INTENTS and runtime_intent == "KNOWLEDGE_REQUIRED"


def _missing_tool_result(response: dict[str, Any]) -> bool:
    payload = response.get("response")
    return (
        isinstance(payload, dict)
        and payload.get("status") == "error"
        and "did not produce a structured response payload" in str(payload.get("answer", ""))
    )


def _missing_action_payload(response: dict[str, Any]) -> bool:
    payload = response.get("response")
    return not (
        isinstance(payload, dict)
        and isinstance(payload.get("action"), dict)
        and isinstance(payload.get("approval"), dict)
    )


def _needs_focus_aoi_fallback(response: dict[str, Any], request: ChatRequest, classified_intent: str) -> bool:
    if classified_intent not in ANALYST_SYNTHESIS_INTENTS:
        return False
    if not (request.region_name and request.aoi):
        return False
    payload = response.get("response")
    if not isinstance(payload, dict):
        return False
    return payload.get("status") == "needs_context"
