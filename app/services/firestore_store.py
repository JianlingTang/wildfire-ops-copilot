from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.models.schemas import (
    ActionRecord,
    AlertRecord,
    ApprovalRecord,
    ReportRecord,
    RunRecord,
    TraceEvent,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class InMemoryStore:
    """Demo Firestore stand-in with the same business boundaries."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.runs: dict[str, RunRecord] = {}
        self.events: dict[str, list[TraceEvent]] = {}
        self.alerts: dict[str, AlertRecord] = {}
        self.actions: dict[str, ActionRecord] = {}
        self.approvals: dict[str, ApprovalRecord] = {}
        self.reports: dict[str, ReportRecord] = {}
        self.audit_logs: list[dict[str, Any]] = []

    def create_run(self, region_id: str, region_name: str) -> RunRecord:
        run = RunRecord(
            run_id=f"run_{uuid4().hex[:10]}",
            region_id=region_id,
            region_name=region_name,
            status="running",
            created_at=utc_now(),
        )
        self.runs[run.run_id] = run
        self.events[run.run_id] = []
        return run

    def complete_run(
        self,
        run_id: str,
        evidence: dict[str, Any],
        risk_assessment: dict[str, Any],
        recommendations: list[str],
    ) -> RunRecord:
        run = self.runs[run_id]
        completed = run.model_copy(
            update={
                "status": "completed",
                "risk_score": risk_assessment["risk_score"],
                "risk_level": risk_assessment["risk_level"],
                "completed_at": utc_now(),
                "evidence": evidence,
                "risk_assessment": risk_assessment,
                "recommendations": recommendations,
            }
        )
        self.runs[run_id] = completed
        return completed

    def get_latest_run(self, region_id: str | None = None) -> RunRecord | None:
        runs = list(self.runs.values())
        if region_id:
            runs = [run for run in runs if run.region_id == region_id]
        completed = [run for run in runs if run.status == "completed"]
        if not completed:
            return None
        return max(completed, key=lambda run: run.completed_at or run.created_at)

    def add_event(self, run_id: str, agent: str, step: str, status: str, summary: str) -> TraceEvent:
        event = TraceEvent(
            run_id=run_id,
            agent=agent,
            step=step,
            status=status,
            summary=summary,
            timestamp=utc_now(),
        )
        self.events.setdefault(run_id, []).append(event)
        return event

    def create_alert(self, payload: dict[str, Any]) -> AlertRecord:
        alert = AlertRecord(
            alert_id=f"alert_{uuid4().hex[:10]}",
            created_at=utc_now(),
            status="active",
            **payload,
        )
        self.alerts[alert.alert_id] = alert
        return alert

    def acknowledge_alert(self, alert_id: str, actor: str) -> AlertRecord:
        alert = self.alerts[alert_id].model_copy(update={"status": "acknowledged"})
        self.alerts[alert_id] = alert
        self.create_audit_log(actor, "ALERT_ACKNOWLEDGED", alert_id, {})
        return alert

    def create_action(self, payload: dict[str, Any]) -> tuple[ActionRecord, ApprovalRecord]:
        action = ActionRecord(
            action_id=f"action_{uuid4().hex[:10]}",
            status="pending_approval",
            created_at=utc_now(),
            **payload,
        )
        approval = ApprovalRecord(
            approval_id=f"approval_{uuid4().hex[:10]}",
            action_id=action.action_id,
            status="pending_approval",
            requested_by=action.requested_by,
            created_at=utc_now(),
        )
        self.actions[action.action_id] = action
        self.approvals[approval.approval_id] = approval
        return action, approval

    def approve_action(self, action_id: str, actor: str) -> tuple[ActionRecord, ApprovalRecord]:
        action = self.actions[action_id].model_copy(update={"status": "approved", "decided_at": utc_now()})
        approval = next(item for item in self.approvals.values() if item.action_id == action_id)
        approval = approval.model_copy(
            update={"status": "approved", "approved_by": actor, "decided_at": utc_now()}
        )
        self.actions[action_id] = action
        self.approvals[approval.approval_id] = approval
        self.create_audit_log(actor, "ACTION_APPROVED", action_id, {})
        return action, approval

    def reject_action(self, action_id: str, actor: str) -> tuple[ActionRecord, ApprovalRecord]:
        action = self.actions[action_id].model_copy(update={"status": "rejected", "decided_at": utc_now()})
        approval = next(item for item in self.approvals.values() if item.action_id == action_id)
        approval = approval.model_copy(update={"status": "rejected", "approved_by": actor, "decided_at": utc_now()})
        self.actions[action_id] = action
        self.approvals[approval.approval_id] = approval
        self.create_audit_log(actor, "ACTION_REJECTED", action_id, {})
        return action, approval

    def create_report(self, payload: dict[str, Any]) -> ReportRecord:
        report = ReportRecord(report_id=f"report_{uuid4().hex[:10]}", created_at=utc_now(), **payload)
        self.reports[report.report_id] = report
        return report

    def create_audit_log(self, actor: str, event_type: str, target_id: str, metadata: dict[str, Any]) -> dict:
        record = {
            "audit_id": f"audit_{uuid4().hex[:10]}",
            "actor": actor,
            "event_type": event_type,
            "target_id": target_id,
            "timestamp": utc_now(),
            "metadata": metadata,
        }
        self.audit_logs.append(record)
        return record


store = InMemoryStore()
