from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from app.models.schemas import (
    ActionRecord,
    AgentEventRecord,
    AlertRecord,
    ApprovalRecord,
    ChatMessageRecord,
    ConversationRecord,
    MonitorTaskRecord,
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
        self.monitor_tasks: dict[str, MonitorTaskRecord] = {}
        self.conversations: dict[str, ConversationRecord] = {}
        self.agent_events: list[AgentEventRecord] = []
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

    def get_or_create_conversation(
        self,
        *,
        conversation_id: str | None,
        user_id: str,
        region_id: str,
        region_name: str | None = None,
        run_id: str | None = None,
    ) -> ConversationRecord:
        existing = self.conversations.get(conversation_id) if conversation_id else None
        # Resume only a conversation the caller owns. An unknown or unowned id starts a
        # fresh conversation instead of raising, so callers cannot probe which ids exist.
        if existing is not None and existing.user_id == user_id:
            updates: dict[str, Any] = {"updated_at": utc_now()}
            if run_id:
                updates["run_id"] = run_id
            if region_name:
                updates["region_name"] = region_name
            conversation = existing.model_copy(update=updates)
            self.conversations[conversation.conversation_id] = conversation
            return conversation

        # Ids are always server-generated. Adopting a client-supplied id would let a caller
        # squat an id that a later caller then joins, exposing the first caller's transcript.
        conversation = ConversationRecord(
            conversation_id=f"conv_{uuid4().hex[:10]}",
            user_id=user_id,
            region_id=region_id,
            region_name=region_name,
            run_id=run_id,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.conversations[conversation.conversation_id] = conversation
        return conversation

    def append_chat_message(
        self,
        conversation_id: str,
        *,
        role: Literal["user", "assistant"],
        content: str,
        intent: str | None = None,
        tool_trace: list[dict[str, Any]] | None = None,
        tool_results: dict[str, Any] | None = None,
        run_id: str | None = None,
        region_id: str | None = None,
    ) -> ChatMessageRecord:
        conversation = self.conversations[conversation_id]
        message = ChatMessageRecord(
            message_id=f"msg_{uuid4().hex[:10]}",
            conversation_id=conversation_id,
            role=role,
            content=content,
            intent=intent,
            tool_trace=tool_trace or [],
            tool_results=tool_results or {},
            run_id=run_id,
            region_id=region_id or conversation.region_id,
            created_at=utc_now(),
        )
        messages = [*conversation.messages, message]
        conversation = conversation.model_copy(update={"messages": messages, "updated_at": utc_now()})
        self.conversations[conversation_id] = conversation
        return message

    def update_conversation_context(
        self,
        conversation_id: str,
        *,
        compressed_context: str | None = None,
        run_id: str | None = None,
        region_name: str | None = None,
    ) -> ConversationRecord:
        conversation = self.conversations[conversation_id]
        updates: dict[str, Any] = {"updated_at": utc_now()}
        if compressed_context is not None:
            updates["compressed_context"] = compressed_context
        if run_id:
            updates["run_id"] = run_id
        if region_name:
            updates["region_name"] = region_name
        conversation = conversation.model_copy(update=updates)
        self.conversations[conversation_id] = conversation
        return conversation

    def get_recent_chat_messages(self, conversation_id: str, limit: int = 6) -> list[ChatMessageRecord]:
        conversation = self.conversations[conversation_id]
        return conversation.messages[-limit:]

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

    def create_monitor_task(self, payload: dict[str, Any]) -> MonitorTaskRecord:
        task = MonitorTaskRecord(task_id=f"monitor_{uuid4().hex[:10]}", created_at=utc_now(), **payload)
        self.monitor_tasks[task.task_id] = task
        self.create_audit_log(task.created_by, "MONITOR_TASK_CREATED", task.task_id, {"region": task.region_name})
        return task

    def update_monitor_task(self, task_id: str, updates: dict[str, Any]) -> MonitorTaskRecord:
        task = self.monitor_tasks[task_id].model_copy(update=updates)
        self.monitor_tasks[task_id] = task
        return task

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

    def append_agent_event(
        self,
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
        event = AgentEventRecord(
            event_id=f"evt_{uuid4().hex[:10]}",
            trace_id=trace_id,
            conversation_id=conversation_id,
            run_id=run_id,
            region_id=region_id,
            agent_type=agent_type,
            status=status,  # type: ignore[arg-type]
            message=message,
            timestamp=utc_now(),
            data=data or {},
        )
        self.agent_events.append(event)
        self.agent_events = self.agent_events[-200:]
        return event


store = InMemoryStore()
