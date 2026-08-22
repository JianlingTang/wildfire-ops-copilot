"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, CheckCircle2, CircleDashed, Clock3, Flame, TriangleAlert, X, XCircle } from "lucide-react";

import { AgentChatBox } from "../components/AgentChatBox";
import { AuthGate } from "../components/AuthGate";
import { AoiSelectionToolbar } from "../components/AoiSelectionToolbar";
import { EvidencePanel } from "../components/EvidencePanel";
import { EmergencyRequestPanel } from "../components/EmergencyRequestPanel";
import { MapDashboard } from "../components/MapDashboard";
import { MobileSidebarSheet } from "../components/MobileSidebarSheet";
import { OperationsSidebar, SupportSection } from "../components/OperationsSidebar";
import { ReportCenter } from "../components/ReportCenter";
import { Badge } from "../components/ui/badge";
import { Card, CardContent } from "../components/ui/card";
import {
  ApiAction,
  ApiAgentEvent,
  ApiAlert,
  ApiHotspotFocus,
  ApiHotspotOverview,
  ApiHotspotVisualization,
  ApiMonitorTask,
  ApiReport,
  ApiRun,
  ApiRequestError,
  ChatApiResult,
  getAgentEventsWebSocketUrl,
  getActions,
  getAlerts,
  getHotspotFocus,
  getHotspotOverview,
  getMonitorTasks,
  getRecentAgentEvents
} from "../lib/api";

type FocusSelection = {
  state: string;
  label: string;
  regionId: string;
  regionName: string;
  center: [number, number];
  radiusKm: number;
  hotspotCount: number;
  hotspots: {
    lat: number;
    lon: number;
    state?: string | null;
    confidence: string;
    detected_at: string;
    power?: number | null;
    satellite?: string | null;
    sensor?: string | null;
  }[];
  source: string;
  statewideHotspotCount: number;
};

const supportMeta: Record<
  SupportSection,
  {
    eyebrow: string;
    title: string;
    description: string;
  }
> = {
  evidence: {
    eyebrow: "Support panel",
    title: "Evidence Sources",
    description: "Review live inputs and Elastic MCP evidence attached to the current run."
  },
  reports: {
    eyebrow: "Support panel",
    title: "Reports",
    description: "Open the saved operational briefs generated from the active analysis."
  }
};

export default function Home() {
  return (
    <AuthGate>
      <OperationsConsole />
    </AuthGate>
  );
}

function OperationsConsole() {
  const mode = "demo";
  const aoiRef = useRef<HTMLDivElement | null>(null);
  const queueRef = useRef<HTMLDivElement | null>(null);
  const supportRef = useRef<HTMLDivElement | null>(null);

  const [activeSupport, setActiveSupport] = useState<SupportSection>("evidence");
  const [activeRun, setActiveRun] = useState<ApiRun | null>(null);
  const [reports, setReports] = useState<ApiReport[]>([]);
  const [alerts, setAlerts] = useState<ApiAlert[]>([]);
  const [actions, setActions] = useState<ApiAction[]>([]);
  const [monitorTasks, setMonitorTasks] = useState<ApiMonitorTask[]>([]);
  const [visualization, setVisualization] = useState<ApiHotspotVisualization | null>(null);
  const [latestAnswer, setLatestAnswer] = useState<string | undefined>(undefined);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [focusLoading, setFocusLoading] = useState(false);
  const [overview, setOverview] = useState<ApiHotspotOverview | null>(null);
  const [focus, setFocus] = useState<ApiHotspotFocus | null>(null);
  const [draftState, setDraftState] = useState("");
  const [draftRadiusKm, setDraftRadiusKm] = useState(50);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [accessNotice, setAccessNotice] = useState<string | null>(null);
  const [agentEvents, setAgentEvents] = useState<ApiAgentEvent[]>([]);

  useEffect(() => {
    let cancelled = false;

    async function loadOverview() {
      setOverviewLoading(true);
      try {
        const payload = await getHotspotOverview();
        if (cancelled) {
          return;
        }
        setOverview(payload);
        setAccessNotice(null);
        setDraftState((current) => {
          if (current) {
            return current;
          }
          const sortedStates = [...payload.data.states].sort(
            (left, right) => right.count_24h - left.count_24h || left.label.localeCompare(right.label)
          );
          return sortedStates[0]?.state ?? payload.data.states[0]?.state ?? "";
        });
      } catch (error) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "Failed to load hotspot overview.";
          if (error instanceof ApiRequestError && error.status === 403) {
            setAccessNotice(message);
          }
          setLatestAnswer(message);
        }
      } finally {
        if (!cancelled) {
          setOverviewLoading(false);
        }
      }
    }

    void loadOverview();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | null = null;
    let pollTimer: number | null = null;

    async function loadRecent() {
      try {
        const payload = await getRecentAgentEvents(20);
        if (!cancelled) {
          setAgentEvents(payload.events);
        }
      } catch {
        // Activity stream is observability-only; do not interrupt the operations console.
      }
    }

    void loadRecent();

    async function connectStream() {
      try {
        socket = new WebSocket(await getAgentEventsWebSocketUrl());
        socket.onmessage = (event) => {
          try {
            const parsed = JSON.parse(event.data) as ApiAgentEvent;
            setAgentEvents((current) => upsertEvent([...current, parsed]).slice(-20));
          } catch {
            // Ignore malformed observability events.
          }
        };
        socket.onerror = () => {
          if (!pollTimer) {
            pollTimer = window.setInterval(loadRecent, 2500);
          }
        };
        socket.onclose = () => {
          if (!cancelled && !pollTimer) {
            pollTimer = window.setInterval(loadRecent, 2500);
          }
        };
      } catch {
        pollTimer = window.setInterval(loadRecent, 2500);
      }
    }

    void connectStream();

    return () => {
      cancelled = true;
      socket?.close();
      if (pollTimer) {
        window.clearInterval(pollTimer);
      }
    };
  }, []);

  useEffect(() => {
    if (!toastMessage) {
      return;
    }
    const timeout = window.setTimeout(() => setToastMessage(null), 4200);
    return () => window.clearTimeout(timeout);
  }, [toastMessage]);

  const stateOptions = useMemo(
    () =>
      [...(overview?.data?.states ?? [])].sort(
        (left, right) => right.count_24h - left.count_24h || left.label.localeCompare(right.label)
      ),
    [overview]
  );
  const draftStateSummary = useMemo(
    () => stateOptions.find((state) => state.state === draftState) ?? null,
    [draftState, stateOptions]
  );
  const focusedSelection = useMemo(() => {
    const focusData = focus?.data;
    if (!focusData) {
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
    } satisfies FocusSelection;
  }, [focus]);

  const currentHotspotCount =
    activeRun?.evidence?.hotspots?.data?.count_24h ??
    focusedSelection?.hotspotCount ??
    overview?.data?.total_count_24h ??
    0;
  const warningCount = activeRun?.evidence?.official_warnings?.data?.incident_count ?? 0;
  const pendingApprovalCount = useMemo(
    () => actions.filter((action) => action.status === "pending_approval").length,
    [actions]
  );
  const evidenceCount = useMemo(() => buildEvidenceSourceCount(activeRun?.evidence), [activeRun?.evidence]);
  const support = supportMeta[activeSupport];
  const focusDescriptor = activeRun?.region_name ?? focusedSelection?.regionName ?? "Australia hotspot overview";

  const clearOperationalState = useCallback(() => {
    setActiveRun(null);
    setReports([]);
    setAlerts([]);
    setActions([]);
    setMonitorTasks([]);
    setVisualization(null);
  }, []);

  const openSupport = useCallback((section: SupportSection) => {
    setActiveSupport(section);
    window.requestAnimationFrame(() => {
      supportRef.current?.scrollIntoView({behavior: "smooth", block: "start"});
    });
  }, []);

  const openQueue = useCallback(() => {
    queueRef.current?.scrollIntoView({behavior: "smooth", block: "start"});
  }, []);

  const requestAoiFocus = useCallback(() => {
    setToastMessage("Select a state and radius, then click Focus AOI before asking the agent.");
    aoiRef.current?.scrollIntoView({behavior: "smooth", block: "start"});
    setLatestAnswer("Select a state and radius, then click Focus AOI before asking the agent.");
  }, []);

  const handleChatResult = useCallback((result: ChatApiResult) => {
    const answer = result.response?.answer ?? result.response?.safety_note ?? result.response?.message;
    if (answer) {
      setLatestAnswer(answer);
    }

    if (result.run) {
      setActiveRun(result.run);
    }

    if (result.report) {
      const report = result.report;
      setReports((current) => upsertById<ApiReport, "report_id">(current, report, "report_id"));
    }

    if (result.alert) {
      const alert = result.alert;
      setAlerts((current) => upsertById<ApiAlert, "alert_id">(current, alert, "alert_id"));
    }

    if (result.response?.visualization) {
      setVisualization(result.response.visualization as ApiHotspotVisualization);
    }

    if (result.response?.monitor_task) {
      setMonitorTasks((current) =>
        upsertById<ApiMonitorTask, "task_id">(current, result.response?.monitor_task as ApiMonitorTask, "task_id")
      );
      openQueue();
    }

    if (result.intent === "ANALYZE_AND_REPORT" || result.intent === "ACTION_COMMAND" || result.intent === "MONITOR_TASK") {
      void (async () => {
        const refreshStartedAt = nowMs();
        try {
          const [alertsResponse, actionsResponse, monitorResponse] = await Promise.all([
            timedClientCall("refresh_alerts", getAlerts),
            timedClientCall("refresh_actions", getActions),
            timedClientCall("refresh_monitor_tasks", getMonitorTasks)
          ]);
          setAlerts((current) => mergeById<ApiAlert, "alert_id">(current, alertsResponse.alerts, "alert_id"));
          setActions((current) => mergeById<ApiAction, "action_id">(current, actionsResponse.actions, "action_id"));
          setMonitorTasks((current) =>
            mergeById<ApiMonitorTask, "task_id">(current, monitorResponse.monitor_tasks, "task_id")
          );
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
      })();
    }
  }, [openQueue]);

  const handleApplyFocus = useCallback(() => {
    if (!draftStateSummary || focusLoading) {
      return;
    }

    clearOperationalState();
    setFocusLoading(true);
    setFocus(null);
    void (async () => {
      try {
        const payload = await getHotspotFocus(draftStateSummary.state, draftRadiusKm);
        setFocus(payload);
        setAccessNotice(null);
        setLatestAnswer(
          `${payload.data.label} is focused on its most active hotspot cluster at ${payload.data.radius_km} km. Run analysis from the AI chatbox to populate risk, warnings, and reports for this AOI.`
        );
      } catch (error) {
        const message = error instanceof Error ? error.message : "Failed to focus the AOI.";
        if (error instanceof ApiRequestError && error.status === 403) {
          setAccessNotice(message);
        }
        setLatestAnswer(message);
      } finally {
        setFocusLoading(false);
      }
    })();
  }, [clearOperationalState, draftRadiusKm, draftStateSummary, focusLoading]);

  const handleResetOverview = useCallback(() => {
    setFocus(null);
    clearOperationalState();
    setLatestAnswer("Showing nationwide hotspots. Select a state and radius, then focus the AOI before running analysis.");
  }, [clearOperationalState]);

  return (
    <main className="min-h-screen bg-background">
      {toastMessage ? (
        <div
          className="fixed right-4 top-20 z-[70] w-[min(calc(100vw-2rem),24rem)] rounded-lg border border-orange-200 bg-orange-50 px-4 py-3 text-orange-950 shadow-lg"
          role="alert"
        >
          <div className="flex items-start gap-3">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-orange-700" />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold">AOI focus required</div>
              <div className="mt-1 text-xs leading-5 text-orange-900">{toastMessage}</div>
            </div>
            <button
              aria-label="Dismiss notification"
              className="rounded p-1 text-orange-700 transition hover:bg-orange-100"
              onClick={() => setToastMessage(null)}
              type="button"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      ) : null}

      <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-background/95 backdrop-blur">
        <div className="flex h-16 items-center justify-between gap-4 px-4 lg:px-6">
          <div className="flex items-center gap-3">
            <MobileSidebarSheet>
              <OperationsSidebar
                activeSection={activeSupport}
                evidenceCount={evidenceCount}
                focusedSelection={
                  focusedSelection
                    ? {
                        regionName: focusedSelection.regionName,
                        radiusKm: focusedSelection.radiusKm
                      }
                    : null
                }
                isOverviewLoading={overviewLoading}
                onSelectSection={openSupport}
                pendingApprovalCount={pendingApprovalCount}
                reportCount={reports.length}
                run={activeRun}
              />
            </MobileSidebarSheet>

            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-md border border-slate-300 bg-white">
                <Flame className="h-5 w-5 text-slate-800" />
              </div>
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Wildfire Ops</div>
                <h1 className="text-lg font-semibold leading-6 text-slate-950 sm:text-2xl">Emergency Operations Console</h1>
              </div>
            </div>
          </div>

          <div className="hidden items-center gap-2 md:flex">
            <Badge variant="outline">Operational</Badge>
            <Badge variant="muted">{focusDescriptor}</Badge>
            <Badge variant="elevated">{currentHotspotCount} hotspots</Badge>
            <Badge variant="outline">{warningCount} warnings</Badge>
            <Badge variant="outline">{pendingApprovalCount} approvals</Badge>
          </div>
        </div>
      </header>

      {accessNotice ? (
        <section className="border-b border-red-200 bg-red-50 px-4 py-3 text-red-950 lg:px-6" role="alert">
          <div className="flex max-w-5xl items-start gap-3">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-red-700" />
            <div className="min-w-0">
              <div className="text-sm font-semibold">Demo access not authorized</div>
              <div className="mt-1 text-sm leading-5 text-red-900">{accessNotice}</div>
            </div>
          </div>
        </section>
      ) : null}

      <div className="p-4 lg:p-5">
        <section className="grid grid-cols-1 gap-4 xl:grid-cols-[232px_minmax(0,1fr)]">
          <aside className="order-2 xl:order-1">
            <OperationsSidebar
              activeSection={activeSupport}
              evidenceCount={evidenceCount}
              focusedSelection={
                focusedSelection
                  ? {
                      regionName: focusedSelection.regionName,
                      radiusKm: focusedSelection.radiusKm
                    }
                  : null
              }
              isOverviewLoading={overviewLoading}
              onSelectSection={openSupport}
              pendingApprovalCount={pendingApprovalCount}
              reportCount={reports.length}
              run={activeRun}
            />
          </aside>

          <div className="order-1 grid gap-4 xl:order-2">
            <div ref={aoiRef}>
              <AoiSelectionToolbar
                appliedSelection={
                  focusedSelection
                    ? {
                        regionName: focusedSelection.regionName,
                        radiusKm: focusedSelection.radiusKm
                      }
                    : null
                }
                draftRadiusKm={draftRadiusKm}
                draftState={draftState}
                isFocusing={focusLoading}
                isLoading={overviewLoading || focusLoading}
                onApply={handleApplyFocus}
                onDraftRadiusChange={setDraftRadiusKm}
                onDraftStateChange={setDraftState}
                onReset={handleResetOverview}
                states={stateOptions}
              />
            </div>

            <CompactSummaryStrip
              hotspotCount={currentHotspotCount}
              pendingApprovalCount={pendingApprovalCount}
              riskLevel={activeRun?.risk_level ?? "STANDBY"}
              riskScore={activeRun?.risk_score}
              warningCount={warningCount}
            />

            <div className="min-h-[460px]">
              <MapDashboard
                overview={overview}
                run={activeRun}
                selectedFocus={focusedSelection}
                visualization={visualization}
              />
            </div>

            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.08fr)_380px]">
              <AgentChatBox
                activeRunId={activeRun?.run_id}
                defaultRegionId={activeRun?.region_id ?? "live_australia"}
                externalAnswer={latestAnswer}
                onNeedAoiFocus={requestAoiFocus}
                onResult={handleChatResult}
                selectedRegion={
                  !focusedSelection
                    ? null
                    : {
                        regionId: focusedSelection.regionId,
                        regionName: focusedSelection.regionName,
                        aoi: {
                          center: focusedSelection.center,
                          radius_km: focusedSelection.radiusKm
                        }
                      }
                }
              />

              <div className="grid gap-4" ref={queueRef}>
                <LiveAgentActivity events={agentEvents} />
                <EmergencyRequestPanel
                  actions={actions}
                  alerts={alerts}
                  className="h-full"
                  mode={mode}
                  monitorTasks={monitorTasks}
                  onActionsChange={setActions}
                  run={activeRun}
                />
              </div>
            </div>

            <div className="grid gap-4" ref={supportRef}>
              <Card className="border-slate-200 shadow-sm">
                <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-end sm:justify-between">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">{support.eyebrow}</div>
                    <div className="mt-1 text-xl font-semibold text-slate-950">{support.title}</div>
                    <div className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">{support.description}</div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="muted">{focusDescriptor}</Badge>
                    <Badge variant="outline">{mode === "demo" ? "Agent workflow" : "Live workflow"}</Badge>
                  </div>
                </CardContent>
              </Card>

              {activeSupport === "evidence" ? <EvidencePanel evidence={activeRun?.evidence} mode={mode} /> : null}
              {activeSupport === "reports" ? <ReportCenter mode={mode} reports={reports} /> : null}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

function LiveAgentActivity({events}: {events: ApiAgentEvent[]}) {
  const visibleEvents = [...events].slice(-12).reverse();
  return (
    <Card className="border-slate-200 shadow-sm">
      <CardContent className="p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
              <Activity className="h-3.5 w-3.5" />
              Live Agent Activity
            </div>
            <div className="mt-1 text-sm text-slate-500">Real-time workflow events and audit summaries.</div>
          </div>
          <Badge variant="outline">{visibleEvents.length} events</Badge>
        </div>

        <div className="mt-4 max-h-[340px] space-y-2 overflow-y-auto pr-1">
          {visibleEvents.length > 0 ? (
            visibleEvents.map((event) => <AgentActivityRow event={event} key={event.event_id} />)
          ) : (
            <div className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-sm text-slate-500">
              Agent events will appear here when analysis, visualization, approvals, or monitor workflows run.
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function AgentActivityRow({event}: {event: ApiAgentEvent}) {
  const Icon =
    event.status === "failed" ? XCircle : event.status === "blocked" ? TriangleAlert : event.status === "started" ? CircleDashed : CheckCircle2;
  const tone =
    event.status === "failed"
      ? "text-red-700"
      : event.status === "blocked"
        ? "text-orange-700"
        : event.status === "started"
          ? "text-blue-700"
          : "text-emerald-700";
  const artifact = event.data?.artifact_id ?? event.data?.tool_name;
  return (
    <div className="rounded-md border border-slate-200 bg-white px-3 py-2">
      <div className="flex items-start gap-2">
        <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
              {labelForAgentType(event.agent_type)}
            </span>
            <span className="inline-flex items-center gap-1 text-[11px] text-slate-400">
              <Clock3 className="h-3 w-3" />
              {shortTime(event.timestamp)}
            </span>
          </div>
          <div className="mt-1 text-sm leading-5 text-slate-800">{event.message}</div>
          {event.data?.output_summary ? (
            <div className="mt-1 truncate text-xs text-slate-500">{String(event.data.output_summary)}</div>
          ) : null}
          {artifact ? <Badge className="mt-2" variant="muted">{String(artifact)}</Badge> : null}
        </div>
      </div>
    </div>
  );
}

function CompactSummaryStrip({
  hotspotCount,
  pendingApprovalCount,
  riskLevel,
  riskScore,
  warningCount
}: {
  hotspotCount: number;
  pendingApprovalCount: number;
  riskLevel: string;
  riskScore?: number | null;
  warningCount: number;
}) {
  const items = [
    {label: "Risk Score", value: riskScore != null ? `${riskScore}/100` : "--", tone: "text-slate-950"},
    {label: "Risk Level", value: riskLevel, tone: riskLevel === "HIGH" || riskLevel === "EXTREME" ? "text-red-700" : "text-slate-950"},
    {label: "Hotspots", value: String(hotspotCount), tone: "text-orange-700"},
    {label: "Warnings", value: String(warningCount), tone: warningCount > 0 ? "text-orange-700" : "text-slate-950"},
    {label: "Approvals", value: String(pendingApprovalCount), tone: pendingApprovalCount > 0 ? "text-orange-700" : "text-slate-950"}
  ];

  return (
    <Card className="border-slate-200 shadow-sm">
      <CardContent className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-5">
        {items.map((item) => (
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3" key={item.label}>
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{item.label}</div>
            <div className={`mt-2 text-2xl font-semibold ${item.tone}`}>{item.value}</div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function upsertById<T extends Record<string, any>, K extends keyof T>(items: T[], item: T, key: K) {
  const existingIndex = items.findIndex((current) => current[key] === item[key]);
  if (existingIndex === -1) {
    return [item, ...items];
  }

  const next = [...items];
  next[existingIndex] = item;
  return next;
}

function mergeById<T extends Record<string, any>, K extends keyof T>(current: T[], incoming: T[], key: K) {
  return incoming.reduce((items, item) => upsertById(items, item, key), current);
}

async function timedClientCall<T>(name: string, call: () => Promise<T>): Promise<T> {
  const startedAt = nowMs();
  try {
    return await call();
  } finally {
    console.info("[chat timing] frontend segment", {name, duration_ms: roundMs(nowMs() - startedAt)});
  }
}

function nowMs() {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

function roundMs(value: number) {
  return Math.round(value * 100) / 100;
}

function upsertEvent(events: ApiAgentEvent[]) {
  const seen = new Map<string, ApiAgentEvent>();
  for (const event of events) {
    seen.set(event.event_id, event);
  }
  return [...seen.values()].sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp));
}

function labelForAgentType(agentType: string) {
  const labels: Record<string, string> = {
    coordinator: "Coordinator",
    analysis: "Analysis",
    elastic: "Elastic",
    risk: "Risk Engine",
    report: "Report Agent",
    approval: "Approval",
    visualization: "Visualization",
    monitor: "Monitor"
  };
  return labels[agentType] ?? agentType;
}

function shortTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--:--";
  }
  return new Intl.DateTimeFormat("en-AU", {hour: "2-digit", minute: "2-digit", second: "2-digit"}).format(date);
}

function buildEvidenceSourceCount(evidence?: Record<string, any> | null) {
  if (!evidence) {
    return 0;
  }
  return ["hotspots", "weather", "official_warnings", "spatial", "elastic"].reduce(
    (count, key) => (evidence[key] ? count + 1 : count),
    0
  );
}

function coerceCenter(center?: [number, number] | number[]) {
  if (!center || center.length !== 2) {
    return null;
  }
  const [lat, lon] = center;
  return Number.isFinite(lat) && Number.isFinite(lon) ? ([lat, lon] as [number, number]) : null;
}
