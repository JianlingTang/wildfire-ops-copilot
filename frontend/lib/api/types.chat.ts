import type { ApiAoi, ApiRiskTrend } from "./types.hotspots";
import type { ApiAlert, ApiReport, ApiRun } from "./types.runs";

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
