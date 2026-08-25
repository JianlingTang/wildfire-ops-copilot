import type { ApiAoi, ApiHotspot, ApiOfficialWarningIncident } from "./types.hotspots";

export type ApiEvidence = {
  region_context?: {
    selection_mode?: string;
    state?: string;
    region_id?: string;
    region_name?: string;
    center?: [number, number] | number[];
    radius_km?: number;
    selected_at?: string;
    hotspot_count_24h?: number;
  };
  hotspots?: {
    status?: string;
    source?: string;
    mode?: string;
    message?: string;
    data?: {
      count_24h?: number;
      count_7d?: number;
      hotspots?: ApiHotspot[];
    };
  };
  official_warnings?: {
    source?: string;
    mode?: string;
    data?: {
      warning_level?: string | null;
      summary?: string;
      issued_time?: string | null;
      incident_count?: number;
      incidents?: ApiOfficialWarningIncident[];
    };
  };
  [key: string]: any;
};

export type RiskRun = {
  run_id: string;
  region_name: string;
  risk_score: number;
  risk_level: string;
  recommendations: string[];
};

export type ApiRun = {
  run_id: string;
  region_id: string;
  region_name: string;
  status: string;
  risk_score: number | null;
  risk_level: string | null;
  created_at: string;
  completed_at: string | null;
  evidence: ApiEvidence;
  risk_assessment: Record<string, any>;
  recommendations: string[];
};

export type ApiTraceEvent = {
  run_id: string;
  agent: string;
  step: string;
  status: "pending" | "running" | "completed" | "failed";
  summary: string;
  timestamp: string;
};

export type ApiAlert = {
  alert_id: string;
  run_id: string;
  region_id: string;
  region_name: string;
  severity: string;
  status: string;
  reason: string;
  evidence_ids: string[];
  recommended_next_action: string;
  created_at: string;
};

export type ApiAction = {
  action_id: string;
  run_id: string | null;
  alert_id: string | null;
  action_type: string;
  title: string;
  draft: string;
  status: string;
  requested_by: string;
  created_at: string;
  decided_at: string | null;
};

export type ApiApproval = {
  approval_id: string;
  action_id: string;
  status: string;
  requested_by: string;
  approved_by: string | null;
  created_at: string;
  decided_at: string | null;
};

export type ApiReport = {
  report_id: string;
  run_id: string;
  type: string;
  title: string;
  markdown: string;
  pdf_url: string | null;
  created_at: string;
};

export type ApiMonitorTask = {
  task_id: string;
  region_id: string;
  region_name: string;
  aoi: ApiAoi;
  interval_minutes: number;
  status: string;
  last_risk_score: number | null;
  last_risk_level: string | null;
  last_checked_at: string | null;
  next_check_at: string;
  created_by: string;
  created_at: string;
};
