import {
  ApiAction,
  ApiAlert,
  ApiHotspotFocus,
  ApiHotspotOverview,
  ApiHotspotVisualization,
  ApiMonitorTask,
  ApiReport,
  ApiRequestError,
  ApiRun,
  ChatApiResult,
  getActions,
  getAlerts,
  getMonitorTasks
} from "../../lib/api";
import { coerceCenter, mergeById, nowMs, roundMs, timedClientCall, upsertById } from "../../lib/operationsConsoleUtils";
import type { FocusSelection } from "./useOperationsData";

export function defaultDraftState(payload: ApiHotspotOverview) {
  const sortedStates = [...payload.data.states].sort(
    (left, right) => right.count_24h - left.count_24h || left.label.localeCompare(right.label)
  );
  return sortedStates[0]?.state ?? payload.data.states[0]?.state ?? "";
}

export function applyLoadError(
  error: unknown,
  setAccessNotice: (value: string | null) => void,
  setLatestAnswer: (value: string | undefined) => void,
  fallbackMessage: string
) {
  const message = error instanceof Error ? error.message : fallbackMessage;
  if (error instanceof ApiRequestError && error.status === 403) {
    setAccessNotice(message);
  }
  setLatestAnswer(message);
}

export function focusSelectionFrom(focus: ApiHotspotFocus | null): FocusSelection | null {
  const focusData = focus?.data;
  if (!focusData || !focus) {
    return null;
  }
  const center = coerceCenter(focusData.center);
  if (!center) {
    return null;
  }
  return {
    state: focusData.state,
    label: focusData.label,
    regionId: focusData.region_id,
    regionName: focusData.region_name,
    center,
    radiusKm: focusData.radius_km,
    hotspotCount: focusData.hotspot_count_24h,
    hotspots: focusData.hotspots,
    source: focus.source,
    statewideHotspotCount: focusData.statewide_hotspot_count_24h
  };
}

export type ChatResultSetters = {
  setLatestAnswer: (value: string | undefined) => void;
  setActiveRun: (value: ApiRun) => void;
  setReports: (updater: (current: ApiReport[]) => ApiReport[]) => void;
  setAlerts: (updater: (current: ApiAlert[]) => ApiAlert[]) => void;
  setVisualization: (value: ApiHotspotVisualization) => void;
  setMonitorTasks: (updater: (current: ApiMonitorTask[]) => ApiMonitorTask[]) => void;
  openQueue: () => void;
};

export function applyChatResultToState(result: ChatApiResult, setters: ChatResultSetters) {
  const answer = result.response?.answer ?? result.response?.safety_note ?? result.response?.message;
  if (answer) {
    setters.setLatestAnswer(answer);
  }
  if (result.run) {
    setters.setActiveRun(result.run);
  }
  if (result.report) {
    const report = result.report;
    setters.setReports((current) => upsertById<ApiReport, "report_id">(current, report, "report_id"));
  }
  if (result.alert) {
    const alert = result.alert;
    setters.setAlerts((current) => upsertById<ApiAlert, "alert_id">(current, alert, "alert_id"));
  }
  if (result.response?.visualization) {
    setters.setVisualization(result.response.visualization as ApiHotspotVisualization);
  }
  if (result.response?.monitor_task) {
    setters.setMonitorTasks((current) =>
      upsertById<ApiMonitorTask, "task_id">(current, result.response?.monitor_task as ApiMonitorTask, "task_id")
    );
    setters.openQueue();
  }
}

export async function refreshAlertsActionsAndMonitorTasks(
  result: ChatApiResult,
  setAlerts: (updater: (current: ApiAlert[]) => ApiAlert[]) => void,
  setActions: (updater: (current: ApiAction[]) => ApiAction[]) => void,
  setMonitorTasks: (updater: (current: ApiMonitorTask[]) => ApiMonitorTask[]) => void
) {
  const refreshStartedAt = nowMs();
  try {
    const [alertsResponse, actionsResponse, monitorResponse] = await Promise.all([
      timedClientCall("refresh_alerts", getAlerts),
      timedClientCall("refresh_actions", getActions),
      timedClientCall("refresh_monitor_tasks", getMonitorTasks)
    ]);
    setAlerts((current) => mergeById<ApiAlert, "alert_id">(current, alertsResponse.alerts, "alert_id"));
    setActions((current) => mergeById<ApiAction, "action_id">(current, actionsResponse.actions, "action_id"));
    setMonitorTasks((current) => mergeById<ApiMonitorTask, "task_id">(current, monitorResponse.monitor_tasks, "task_id"));
    console.info("[chat timing] frontend refresh", {
      trace_id: result.trace_id,
      intent: result.intent,
      total_ms: roundMs(nowMs() - refreshStartedAt),
      chat_api_fetch_ms: result.client_timing?.chat_api_fetch_ms,
      backend_total_ms: result.timing_trace?.total_ms,
      backend_api_total_ms: result.timing_trace?.api_total_ms
    });
  } catch (error) {
    console.error("Failed to refresh alerts or actions", error);
  }
}
