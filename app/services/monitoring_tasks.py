from __future__ import annotations

import asyncio
import re
from datetime import timedelta
from typing import Any

from app.models.schemas import ChatRequest, MonitorTaskRecord
from app.runtime.analysis import execute_analysis_request
from app.services.firestore_store import store, utc_now
from app.tools.fire_hotspot_tools import resolve_operational_region

_MONITOR_LOOP_STARTED = False
DEFAULT_MONITOR_INTERVAL_MINUTES = 10
_INTERVAL_PATTERN = re.compile(r"\b(\d{1,4})\s*-?\s*(minutes?|mins?|hours?|hrs?)\b", re.IGNORECASE)


def create_monitor_task_from_chat(request: ChatRequest, interval_minutes: int | None = None) -> dict[str, Any]:
    resolved_interval_minutes = interval_minutes or _parse_interval_minutes(request.message) or DEFAULT_MONITOR_INTERVAL_MINUTES
    region = resolve_operational_region(
        request.region_id,
        request.region_name or request.region_id.replace("_", " ").title(),
        request.aoi,
        respect_explicit_aoi=bool(request.aoi and request.aoi.center),
    )
    task = store.create_monitor_task(
        {
            "region_id": region["region_id"],
            "region_name": region["region_name"],
            "aoi": region["aoi"],
            "interval_minutes": resolved_interval_minutes,
            "next_check_at": utc_now() + timedelta(minutes=resolved_interval_minutes),
            "created_by": request.user_id,
        }
    )
    return {
        "status": "success",
        "mode": "adk",
        "monitor_task": task,
        "answer": (
            f"Created an active monitor task for {task.region_name}. "
            f"It will refresh risk every {task.interval_minutes} minutes while the backend instance is running "
            "and create an alert if the score jumps materially."
        ),
        "tool_trace": [
            _trace_item("Main Coordinator", "Selected Monitor Task Workflow.", task.region_name),
            _trace_item(
                "Monitoring Scheduler",
                "Created recurring risk check.",
                f"{task.interval_minutes} minute interval",
            ),
            _trace_item("Alert Rule", "Configured material-change alerting.", "score delta >= 12"),
        ],
    }


def _parse_interval_minutes(message: str) -> int | None:
    match = _INTERVAL_PATTERN.search(message)
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("hour") or unit.startswith("hr"):
        return value * 60
    return value


def list_monitor_tasks() -> list[MonitorTaskRecord]:
    return sorted(store.monitor_tasks.values(), key=lambda task: task.created_at, reverse=True)


def start_monitor_loop() -> None:
    global _MONITOR_LOOP_STARTED
    if _MONITOR_LOOP_STARTED:
        return
    _MONITOR_LOOP_STARTED = True
    try:
        asyncio.create_task(_monitor_loop())
    except RuntimeError:
        _MONITOR_LOOP_STARTED = False


async def _monitor_loop() -> None:
    while True:
        await asyncio.sleep(600)
        for task in list(store.monitor_tasks.values()):
            if task.status != "active":
                continue
            if task.next_check_at > utc_now():
                continue
            await asyncio.to_thread(_run_monitor_check, task)


def _run_monitor_check(task: MonitorTaskRecord) -> None:
    request = ChatRequest(
        message="Scheduled monitor risk refresh.",
        region_id=task.region_id,
        region_name=task.region_name,
        aoi=task.aoi,
        user_id=task.created_by,
    )
    artifacts = execute_analysis_request(request, route_label="monitor_task")
    previous_score = task.last_risk_score
    current_score = artifacts.run.risk_score or 0
    current_level = artifacts.run.risk_level
    updates = {
        "last_risk_score": current_score,
        "last_risk_level": current_level,
        "last_checked_at": utc_now(),
        "next_check_at": utc_now() + timedelta(minutes=task.interval_minutes),
    }
    store.update_monitor_task(task.task_id, updates)
    if previous_score is not None and abs(current_score - previous_score) >= 12:
        store.create_alert(
            {
                "run_id": artifacts.run.run_id,
                "region_id": artifacts.run.region_id,
                "region_name": artifacts.run.region_name,
                "severity": current_level or "HIGH",
                "reason": f"Monitor task detected risk score change from {previous_score} to {current_score}.",
                "evidence_ids": [],
                "recommended_next_action": "Review the refreshed analysis and inspect the changed hotspot contour.",
            }
        )


def _trace_item(called: str, did: str, output: Any) -> dict[str, Any]:
    return {"called": called, "did": did, "output": str(output), "mode": "adk", "status": "completed"}
