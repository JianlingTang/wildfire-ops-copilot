from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AlertStatus = Literal["active", "acknowledged", "resolved", "pending_review"]
ActionStatus = Literal["drafted", "pending_approval", "approved", "rejected", "executed", "failed"]
RiskLevel = Literal["LOW", "MODERATE", "HIGH", "EXTREME"]


class Aoi(BaseModel):
    bbox: list[float] | None = Field(default=None, description="[west, south, east, north]")
    center: tuple[float, float] | None = Field(default=(-33.71, 150.31), description="lat/lon")
    radius_km: float = 30


class ManualRunRequest(BaseModel):
    region_id: str = "live_australia"
    region_name: str = "Australia Live Hotspot AOI"
    aoi: Aoi = Field(default_factory=Aoi)


class DailyRunRequest(BaseModel):
    region_ids: list[str] | None = None


class ChatRequest(BaseModel):
    message: str
    run_id: str | None = None
    region_id: str = "live_australia"
    region_name: str | None = None
    aoi: Aoi | None = None
    user_id: str = "demo_officer"


class AcknowledgeAlertRequest(BaseModel):
    actor: str = "demo_officer"


class ApprovalDecisionRequest(BaseModel):
    actor: str = "demo_officer"


class RunRecord(BaseModel):
    run_id: str
    region_id: str
    region_name: str
    status: str
    risk_score: int | None = None
    risk_level: RiskLevel | None = None
    created_at: datetime
    completed_at: datetime | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    risk_assessment: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


class TraceEvent(BaseModel):
    run_id: str
    agent: str
    step: str
    status: str
    summary: str
    timestamp: datetime


class AlertRecord(BaseModel):
    alert_id: str
    run_id: str
    region_id: str
    region_name: str
    severity: RiskLevel
    status: AlertStatus
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    recommended_next_action: str
    created_at: datetime


class ActionRecord(BaseModel):
    action_id: str
    run_id: str | None = None
    alert_id: str | None = None
    action_type: str
    title: str
    draft: str
    status: ActionStatus
    requested_by: str
    created_at: datetime
    decided_at: datetime | None = None


class ApprovalRecord(BaseModel):
    approval_id: str
    action_id: str
    status: Literal["pending_approval", "approved", "rejected"]
    requested_by: str
    approved_by: str | None = None
    created_at: datetime
    decided_at: datetime | None = None


class ReportRecord(BaseModel):
    report_id: str
    run_id: str
    type: str
    title: str
    markdown: str
    pdf_url: str | None = None
    created_at: datetime


class MonitorTaskRecord(BaseModel):
    task_id: str
    region_id: str
    region_name: str
    aoi: Aoi
    interval_minutes: int = 10
    status: Literal["active", "paused", "failed"] = "active"
    last_risk_score: int | None = None
    last_risk_level: RiskLevel | None = None
    last_checked_at: datetime | None = None
    next_check_at: datetime
    created_by: str
    created_at: datetime
