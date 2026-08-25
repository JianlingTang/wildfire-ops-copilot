from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

AlertStatus = Literal["active", "acknowledged", "resolved", "pending_review"]
ActionStatus = Literal["drafted", "pending_approval", "approved", "rejected", "executed", "failed"]
RiskLevel = Literal["LOW", "MODERATE", "HIGH", "EXTREME"]


class Aoi(BaseModel):
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4, description="[west, south, east, north]")
    center: tuple[float, float] | None = Field(default=(-33.71, 150.31), description="lat/lon")
    radius_km: float = Field(default=30, ge=1, le=200)

    @field_validator("center")
    @classmethod
    def validate_center(cls, center: tuple[float, float] | None) -> tuple[float, float] | None:
        if center is None:
            return center
        lat, lon = center
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("center must be a valid lat/lon pair")
        return center

    @model_validator(mode="after")
    def validate_bbox(self) -> "Aoi":
        if not self.bbox:
            return self
        west, south, east, north = self.bbox
        if not -180 <= west <= 180 or not -180 <= east <= 180:
            raise ValueError("bbox longitude values must be between -180 and 180")
        if not -90 <= south <= 90 or not -90 <= north <= 90:
            raise ValueError("bbox latitude values must be between -90 and 90")
        if west >= east or south >= north:
            raise ValueError("bbox must be ordered as west, south, east, north")
        return self


class ManualRunRequest(BaseModel):
    region_id: str = "live_australia"
    region_name: str = "Australia Live Hotspot AOI"
    aoi: Aoi = Field(default_factory=Aoi)


class DailyRunRequest(BaseModel):
    region_ids: list[str] | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=128)
    run_id: str | None = Field(default=None, max_length=128)
    region_id: str = Field(default="live_australia", max_length=128)
    region_name: str | None = Field(default=None, max_length=256)
    aoi: Aoi | None = None
    user_id: str = Field(default="demo_officer", max_length=128)


class AcknowledgeAlertRequest(BaseModel):
    actor: str = Field(default="demo_officer", min_length=1, max_length=128)


class ApprovalDecisionRequest(BaseModel):
    actor: str = Field(default="demo_officer", min_length=1, max_length=128)


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


class AgentEventRecord(BaseModel):
    event_id: str
    trace_id: str
    conversation_id: str | None = None
    run_id: str | None = None
    region_id: str | None = None
    agent_type: str
    status: Literal["started", "completed", "failed", "blocked"]
    message: str
    timestamp: datetime
    data: dict[str, Any] = Field(default_factory=dict)


class ChatMessageRecord(BaseModel):
    message_id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    intent: str | None = None
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: dict[str, Any] = Field(default_factory=dict)
    run_id: str | None = None
    region_id: str | None = None
    created_at: datetime


class ConversationRecord(BaseModel):
    conversation_id: str
    user_id: str
    region_id: str
    region_name: str | None = None
    run_id: str | None = None
    compressed_context: str = ""
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessageRecord] = Field(default_factory=list)


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
