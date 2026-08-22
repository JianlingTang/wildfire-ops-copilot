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

import { getFirebaseIdToken, getFirebaseUserEmail } from "./firebaseAuth";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001";

export class ApiRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

async function apiHeaders(headers: HeadersInit = {}): Promise<HeadersInit> {
  const idToken = await getFirebaseIdToken();
  return idToken ? {...headers, Authorization: `Bearer ${idToken}`} : headers;
}

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
  preview?: {
    format: string;
    encoding: string;
    data_url: string;
    width: number;
    height: number;
    alt: string;
  };
  interpretation: {
    summary: string;
    cluster_center: [number, number] | number[];
    priority: string;
    recommendation: string;
    caveat: string;
  };
  downloads: {
    txt_filename?: string;
    txt_content?: string;
    png_filename?: string;
    json_filename?: string;
    csv_filename?: string;
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

export type ApiRiskTrend = {
  points: {
    run_id?: string;
    risk_score: number;
    risk_level: string;
    date: string;
    type: "historical" | "current" | "forecast";
  }[];
  note: string;
  region_name: string;
  preview?: {
    format: string;
    encoding: string;
    data_url: string;
    alt: string;
  };
  downloads?: {
    png_filename?: string;
  };
  prediction?: Record<string, any>;
};

export type ChatApiResult = {
  intent: string;
  mode?: string;
  trace_id?: string;
  timing_trace?: {
    intent?: string;
    total_ms?: number;
    api_total_ms?: number;
    steps?: {
      name: string;
      duration_ms: number;
      status: string;
      detail?: Record<string, any>;
    }[];
  };
  client_timing?: Record<string, number>;
  response?: Record<string, any> & {risk_trend?: ApiRiskTrend};
  run?: ApiRun;
  report?: ApiReport;
  alert?: ApiAlert | null;
  conversation_id?: string;
  messages?: ApiChatMessage[];
  context_summary?: string;
  requires_analysis?: boolean;
};

export type ApiAgentEvent = {
  event_id: string;
  trace_id: string;
  conversation_id?: string | null;
  run_id?: string | null;
  region_id?: string | null;
  agent_type: string;
  status: "started" | "completed" | "failed" | "blocked";
  message: string;
  timestamp: string;
  data: Record<string, any>;
};

export type ChatRequestOptions = {
  conversationId?: string;
  runId?: string;
  regionId?: string;
  regionName?: string;
  aoi?: ApiAoi;
};

export type ApiChatMessage = {
  message_id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  intent?: string | null;
  tool_trace?: Record<string, any>[];
  tool_results?: Record<string, any>;
  run_id?: string | null;
  region_id?: string | null;
  created_at: string;
};

export async function startManualRun() {
  const response = await fetch(`${API_BASE_URL}/api/runs/manual`, {
    method: "POST",
    headers: await apiHeaders({"Content-Type": "application/json"}),
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
  const startedAt = nowMs();
  const {
    conversationId,
    runId,
    regionId = "live_australia",
    regionName,
    aoi
  } = options;
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: await apiHeaders({"Content-Type": "application/json"}),
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      run_id: runId,
      region_id: regionId,
      region_name: regionName,
      aoi
    })
  });
  if (!response.ok) {
    throw new Error("Chat request failed");
  }
  const payload = await response.json();
  return {
    ...payload,
    client_timing: {
      ...(payload.client_timing ?? {}),
      chat_api_fetch_ms: roundMs(nowMs() - startedAt)
    }
  };
}

function nowMs() {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

function roundMs(value: number) {
  return Math.round(value * 100) / 100;
}

export async function getHotspotOverview(): Promise<ApiHotspotOverview> {
  const response = await fetch(`${API_BASE_URL}/api/hotspots/overview`, {cache: "no-store", headers: await apiHeaders()});
  return parseHotspotResponse<ApiHotspotOverview>(response, "Failed to load hotspot overview");
}

export async function getHotspotFocus(state: string, radiusKm: number): Promise<ApiHotspotFocus> {
  const params = new URLSearchParams({state, radius_km: String(radiusKm)});
  const response = await fetch(`${API_BASE_URL}/api/hotspots/focus?${params.toString()}`, {cache: "no-store", headers: await apiHeaders()});
  return parseHotspotResponse<ApiHotspotFocus>(response, "Failed to load hotspot focus");
}

async function parseHotspotResponse<T extends {status: string; message?: string; data: unknown}>(
  response: Response,
  fallbackMessage: string
): Promise<T> {
  const payload = (await response.json().catch(() => null)) as T | null;
  if (response.status === 403) {
    const email = getFirebaseUserEmail();
    throw new ApiRequestError(
      [
        email ? `Signed in as ${email}.` : "Signed in account is not authorized.",
        "This account is not authorized for this demo.",
        "Please use the approved operator account."
      ].join(" "),
      response.status
    );
  }
  if (response.status === 401) {
    throw new ApiRequestError("Please sign in with an approved Google account for this demo.", response.status);
  }
  if (!response.ok || payload?.status !== "success" || !payload.data) {
    throw new ApiRequestError(payload?.message ?? fallbackMessage, response.status);
  }
  return payload;
}

export async function getRunEvents(runId: string): Promise<{events: ApiTraceEvent[]}> {
  const response = await fetch(`${API_BASE_URL}/api/runs/${runId}/events`, {headers: await apiHeaders()});
  if (!response.ok) {
    throw new Error("Failed to load run events");
  }
  return response.json();
}

export async function getRecentAgentEvents(limit = 20): Promise<{events: ApiAgentEvent[]}> {
  const params = new URLSearchParams({limit: String(limit)});
  const response = await fetch(`${API_BASE_URL}/api/agent-events/recent?${params.toString()}`, {headers: await apiHeaders()});
  if (!response.ok) {
    throw new Error("Failed to load agent activity");
  }
  return response.json();
}

export function getAgentEventsWebSocketUrl() {
  const base = new URL(API_BASE_URL);
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  base.pathname = "/api/agent-events/ws";
  return base.toString();
}

// The credential travels in the first frame, not the URL: query strings are recorded in
// access logs and proxy history. Browsers cannot set headers on a WebSocket handshake,
// so the first frame is the way to keep it out of the URL.
export async function openAgentEventsSocket(): Promise<WebSocket> {
  const idToken = await getFirebaseIdToken();
  const socket = new WebSocket(getAgentEventsWebSocketUrl());
  socket.addEventListener(
    "open",
    () => {
      if (idToken) {
        socket.send(JSON.stringify({type: "auth", token: idToken}));
      }
    },
    {once: true}
  );
  return socket;
}

export async function getAlerts(): Promise<{alerts: ApiAlert[]}> {
  const response = await fetch(`${API_BASE_URL}/api/alerts`, {headers: await apiHeaders()});
  if (!response.ok) {
    throw new Error("Failed to load alerts");
  }
  return response.json();
}

export async function getActions(): Promise<{actions: ApiAction[]; approvals: ApiApproval[]}> {
  const response = await fetch(`${API_BASE_URL}/api/actions`, {headers: await apiHeaders()});
  if (!response.ok) {
    throw new Error("Failed to load actions");
  }
  return response.json();
}

export async function approveAction(actionId: string, actor = "demo_officer"): Promise<{action: ApiAction; approval: ApiApproval}> {
  const response = await fetch(`${API_BASE_URL}/api/actions/${actionId}/approve`, {
    method: "POST",
    headers: await apiHeaders({"Content-Type": "application/json"}),
    body: JSON.stringify({actor})
  });
  if (!response.ok) {
    throw new Error("Failed to approve action");
  }
  return response.json();
}

export async function rejectAction(actionId: string, actor = "demo_officer"): Promise<{action: ApiAction; approval: ApiApproval}> {
  const response = await fetch(`${API_BASE_URL}/api/actions/${actionId}/reject`, {
    method: "POST",
    headers: await apiHeaders({"Content-Type": "application/json"}),
    body: JSON.stringify({actor})
  });
  if (!response.ok) {
    throw new Error("Failed to decline action");
  }
  return response.json();
}

export async function getMonitorTasks(): Promise<{monitor_tasks: ApiMonitorTask[]}> {
  const response = await fetch(`${API_BASE_URL}/api/monitor-tasks`, {headers: await apiHeaders()});
  if (!response.ok) {
    throw new Error("Failed to load monitor tasks");
  }
  return response.json();
}
