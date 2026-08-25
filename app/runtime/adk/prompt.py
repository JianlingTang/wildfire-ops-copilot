"""Operator-context prompt construction for the ADK LlmAgent turn."""

from __future__ import annotations

import json
from typing import Any

from app.models.schemas import ChatRequest, RunRecord
from app.runtime.adk.dispatch import _resolve_run_for_request
from app.services.firestore_store import store


def _message_with_operational_context(request: ChatRequest) -> str:
    context = _context_json_for_request(request)
    compressed_context = _compressed_context(request)
    return (
        f"Operator request: {request.message}\n"
        f"context_json: {json.dumps(context, default=str)}\n"
        f"Compressed conversation context: {compressed_context or 'none'}\n"
        "Select exactly one provided tool. Prefer a deterministic workflow or calculation tool whenever it can "
        "answer the exact request. Never answer directly from context_json or model memory. Use "
        "conversation_memory_lookup_tool for exact prior-question, selected-AOI, report-AOI, or action-status "
        "state. Use analyst_question_tool for operational evidence synthesis. Use "
        "knowledge_retrieval_required_tool when no deterministic tool can answer; do not invent a knowledge answer. "
        "When a tool returns structured evidence, synthesize the final answer for the exact requested dimension. "
        "If the evidence packet includes missing baseline data, say what is missing instead of answering a nearby "
        "question. "
        "When calling a workflow tool, pass the operator request and any available region_id, region_name, "
        "aoi_center, radius_km, run_id, and user_id values."
    )


def _compressed_context(request: ChatRequest) -> str:
    conversation = store.conversations.get(request.conversation_id or "")
    return conversation.compressed_context if conversation else ""


def _context_json_for_request(request: ChatRequest) -> dict[str, Any]:
    run = _resolve_run_for_request(request)
    selected_aoi = _base_selected_aoi(request)
    latest_run = None
    evidence_summary: dict[str, Any] = {}
    if run:
        latest_run = _latest_run_summary(run)
        _apply_region_context_defaults(selected_aoi, run)
        evidence_summary = _evidence_summary(run)
    return {"selected_aoi": selected_aoi, "latest_run": latest_run, "evidence": evidence_summary}


def _base_selected_aoi(request: ChatRequest) -> dict[str, Any]:
    selected_aoi: dict[str, Any] = {
        "region_id": request.region_id,
        "region_name": request.region_name,
        "run_id": request.run_id,
        "conversation_id": request.conversation_id,
    }
    if request.aoi and request.aoi.center:
        selected_aoi["center"] = list(request.aoi.center)
        selected_aoi["radius_km"] = request.aoi.radius_km
    return selected_aoi


def _apply_region_context_defaults(selected_aoi: dict[str, Any], run: RunRecord) -> None:
    region_context = run.evidence.get("region_context", {})
    if region_context:
        selected_aoi.setdefault("center", region_context.get("center"))
        selected_aoi.setdefault("radius_km", region_context.get("radius_km"))


def _latest_run_summary(run: RunRecord) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "region_id": run.region_id,
        "region_name": run.region_name,
        "risk_score": run.risk_score,
        "risk_level": run.risk_level,
        "drivers": run.risk_assessment.get("drivers", []),
        "recommendations": run.recommendations,
    }


def _evidence_summary(run: RunRecord) -> dict[str, Any]:
    elastic = run.evidence.get("elastic", {})
    return {
        "region_context": run.evidence.get("region_context", {}),
        "hotspots": run.evidence.get("hotspots", {}).get("data", {}),
        "weather": run.evidence.get("weather", {}).get("data", {}),
        "spatial": run.evidence.get("spatial", {}).get("data", {}),
        "official_warnings": run.evidence.get("official_warnings", {}).get("data", {}),
        "elastic": {
            "mode": elastic.get("mode"),
            "evidence": elastic.get("evidence", [])[:3],
        },
    }
