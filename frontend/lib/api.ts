export type ApiHotspot = {
  lat: number;
  lon: number;
  state?: string | null;
  confidence: string;
  detected_at: string;
  power?: number | null;
  satellite?: string | null;
  sensor?: string | null;
};

export type ApiAoi = {
  bbox?: number[] | null;
  center?: [number, number] | number[];
  radius_km: number;
};

export type ApiHotspotStateSummary = {
  state: string;
  label: string;
  count_24h: number;
  center: [number, number] | number[];
  region_id: string;
  region_name: string;
  radius_options_km: number[];
};

export type ApiHotspotOverview = {
  status: string;
  mode: string;
  source: string;
  cached?: boolean;
  cache_ttl_seconds?: number;
  data: {
    time_window: string;
    updated_at: string;
    total_count_24h: number;
    display_hotspot_count?: number;
    hotspots: ApiHotspot[];
    states: ApiHotspotStateSummary[];
  };
  message?: string;
};

export type ApiHotspotFocus = {
  status: string;
  mode: string;
  source: string;
  cached?: boolean;
  cache_ttl_seconds?: number;
  data: {
    state: string;
    label: string;
    region_id: string;
    region_name: string;
    center: [number, number] | number[];
    radius_km: number;
    hotspot_count_24h: number;
    statewide_hotspot_count_24h: number;
    display_hotspot_count?: number;
    hotspots: ApiHotspot[];
  };
  message?: string;
};

export type ApiOfficialWarningIncident = {
  title: string;
  category: string;
  alert_level: string;
  status: string;
  location: string;
  distance_km: number;
  lat?: number;
  lon?: number;
  updated_at: string | null;
  guid?: string | null;
};

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
    source?: string;
    mode?: string;
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

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001";

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

export type ApiHotspotVisualization = {
  status: string;
  mode: string;
  region: {
    region_id: string;
    region_name: string;
    center: [number, number] | number[];
    radius_km: number;
  };
  source: string;
  generated_at: string;
  hotspot_count: number;
  heatmap: {
    cells: {
      lat: number;
      lon: number;
      density: number;
      max_power: number;
      latest_detection: string;
      normalized_intensity: number;
    }[];
    intensity_field: string;
  };
  contours: {
    type: "FeatureCollection";
    features: {
      type: "Feature";
      properties: {
        band: string;
        threshold: number;
        color: string;
        radius_km: number;
      };
      geometry: {
        type: "Polygon";
        coordinates: number[][][];
      };
    }[];
  };
  interpretation: {
    summary: string;
    cluster_center: [number, number] | number[];
    priority: string;
    recommendation: string;
    caveat: string;
  };
  downloads: {
    json_filename: string;
    csv_filename: string;
  };
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

export type ChatApiResult = {
  intent: string;
  mode?: string;
  response?: Record<string, any>;
  run?: ApiRun;
  report?: ApiReport;
  alert?: ApiAlert | null;
};

export type ChatRequestOptions = {
  runId?: string;
  regionId?: string;
  regionName?: string;
  aoi?: ApiAoi;
};

export async function startManualRun() {
  const response = await fetch(`${API_BASE_URL}/api/runs/manual`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({region_id: "live_australia", region_name: "Australia Live Hotspot AOI"})
  });
  if (!response.ok) {
    throw new Error("Manual run failed");
  }
  return response.json();
}

export async function sendChat(
  message: string,
  options: ChatRequestOptions = {}
): Promise<ChatApiResult> {
  const {
    runId,
    regionId = "live_australia",
    regionName,
    aoi
  } = options;
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      message,
      run_id: runId,
      region_id: regionId,
      region_name: regionName,
      aoi
    })
  });
  if (!response.ok) {
    throw new Error("Chat request failed");
  }
  return response.json();
}

export async function getHotspotOverview(): Promise<ApiHotspotOverview> {
  const response = await fetch(`${API_BASE_URL}/api/hotspots/overview`);
  if (!response.ok) {
    throw new Error("Failed to load hotspot overview");
  }
  return response.json();
}

export async function getHotspotFocus(state: string, radiusKm: number): Promise<ApiHotspotFocus> {
  const params = new URLSearchParams({state, radius_km: String(radiusKm)});
  const response = await fetch(`${API_BASE_URL}/api/hotspots/focus?${params.toString()}`);
  if (!response.ok) {
    throw new Error("Failed to load hotspot focus");
  }
  return response.json();
}

export async function getRunEvents(runId: string): Promise<{events: ApiTraceEvent[]}> {
  const response = await fetch(`${API_BASE_URL}/api/runs/${runId}/events`);
  if (!response.ok) {
    throw new Error("Failed to load run events");
  }
  return response.json();
}

export async function getAlerts(): Promise<{alerts: ApiAlert[]}> {
  const response = await fetch(`${API_BASE_URL}/api/alerts`);
  if (!response.ok) {
    throw new Error("Failed to load alerts");
  }
  return response.json();
}

export async function getActions(): Promise<{actions: ApiAction[]; approvals: ApiApproval[]}> {
  const response = await fetch(`${API_BASE_URL}/api/actions`);
  if (!response.ok) {
    throw new Error("Failed to load actions");
  }
  return response.json();
}

export async function getMonitorTasks(): Promise<{monitor_tasks: ApiMonitorTask[]}> {
  const response = await fetch(`${API_BASE_URL}/api/monitor-tasks`);
  if (!response.ok) {
    throw new Error("Failed to load monitor tasks");
  }
  return response.json();
}
