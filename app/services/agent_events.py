from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import uuid4

import anyio
from fastapi import WebSocket

from app.models.schemas import AgentEventRecord
from app.services.firestore_store import store

VALID_STATUSES = {"started", "completed", "failed", "blocked"}


def new_trace_id() -> str:
    return f"trace_{uuid4().hex[:12]}"


class AgentEventHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    async def broadcast(self, event: AgentEventRecord) -> None:
        if not self._clients:
            return
        payload = event.model_dump(mode="json")
        disconnected: list[WebSocket] = []
        for client in list(self._clients):
            try:
                await client.send_json(payload)
            except Exception:
                disconnected.append(client)
        for client in disconnected:
            self.disconnect(client)


hub = AgentEventHub()


def publish_agent_event(
    *,
    trace_id: str,
    agent_type: str,
    status: str,
    message: str,
    conversation_id: str | None = None,
    run_id: str | None = None,
    region_id: str | None = None,
    data: dict[str, Any] | None = None,
) -> AgentEventRecord:
    event = store.append_agent_event(
        trace_id=trace_id,
        agent_type=agent_type,
        status=status if status in VALID_STATUSES else "completed",
        message=message,
        conversation_id=conversation_id,
        run_id=run_id,
        region_id=region_id,
        data=data,
    )
    _schedule_broadcast(event)
    _write_bigquery_event(event)
    return event


def recent_agent_events(limit: int = 20) -> list[AgentEventRecord]:
    return store.agent_events[-max(1, min(limit, 100)) :]


def publish_trace_items(
    *,
    trace_id: str,
    tool_trace: list[dict[str, Any]],
    conversation_id: str | None = None,
    run_id: str | None = None,
    region_id: str | None = None,
) -> None:
    for item in tool_trace:
        called = str(item.get("called") or "Agent")
        did = str(item.get("did") or "Completed workflow step.")
        output = str(item.get("output") or item.get("next_step") or "")
        status = _event_status(str(item.get("status") or "completed"))
        publish_agent_event(
            trace_id=trace_id,
            conversation_id=conversation_id,
            run_id=run_id,
            region_id=region_id,
            agent_type=_agent_type_for_trace(called),
            status=status,
            message=f"{called}: {did}",
            data={
                "tool_name": called,
                "output_summary": output,
                "mode": item.get("mode"),
            },
        )


def _schedule_broadcast(event: AgentEventRecord) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            anyio.from_thread.run(hub.broadcast, event)
        except Exception:
            return
        return
    loop.create_task(hub.broadcast(event))


def _write_bigquery_event(event: AgentEventRecord) -> None:
    if os.getenv("AUDIT_SINK", "in_memory").strip().lower() != "bigquery":
        return
    table = os.getenv("BIGQUERY_AUDIT_TABLE", "").strip()
    if not table:
        return
    try:
        from google.cloud import bigquery  # type: ignore[import-not-found]

        client = bigquery.Client()
        errors = client.insert_rows_json(table, [event.model_dump(mode="json")])
        if errors:
            raise RuntimeError(str(errors))
    except Exception as exc:
        store.create_audit_log(
            actor="system",
            event_type="AUDIT_SINK_FAILED",
            target_id=event.event_id,
            metadata={"sink": "bigquery", "error": str(exc)},
        )


def _event_status(status: str) -> str:
    if status in {"running", "started", "pending"}:
        return "started"
    if status == "failed":
        return "failed"
    if status == "blocked":
        return "blocked"
    return "completed"


def _agent_type_for_trace(called: str) -> str:
    lowered = called.lower()
    if "elastic" in lowered:
        return "elastic"
    if "risk" in lowered:
        return "risk"
    if "report" in lowered:
        return "report"
    if "approval" in lowered or "action" in lowered or "safety" in lowered:
        return "approval"
    if "visual" in lowered or "heatmap" in lowered or "density" in lowered or "contour" in lowered:
        return "visualization"
    if "monitor" in lowered or "scheduler" in lowered:
        return "monitor"
    if "analysis" in lowered or "external data" in lowered:
        return "analysis"
    return "coordinator"
