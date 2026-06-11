import { useState } from "react";
import { Activity, CheckCircle2, FileText, ShieldAlert, TriangleAlert, XCircle } from "lucide-react";

import { ApiAction, ApiAlert, ApiMonitorTask, ApiOfficialWarningIncident, ApiRun, approveAction, rejectAction } from "../lib/api";
import { cn } from "../lib/utils";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

export function EmergencyRequestPanel({
  actions = [],
  alerts = [],
  monitorTasks = [],
  run,
  className,
  mode = "demo",
  onActionsChange
}: {
  actions?: ApiAction[];
  alerts?: ApiAlert[];
  monitorTasks?: ApiMonitorTask[];
  run?: ApiRun | null;
  className?: string;
  mode?: string;
  onActionsChange?: (actions: ApiAction[] | ((current: ApiAction[]) => ApiAction[])) => void;
}) {
  const [expandedActionId, setExpandedActionId] = useState<string | null>(null);
  const [busyActionId, setBusyActionId] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const pendingActions = actions.filter((action) => action.status === "pending_approval");
  const warningSource = run?.evidence?.official_warnings?.source ?? "Official warning feed";
  const warningSummary = run?.evidence?.official_warnings?.data?.summary;
  const warnings = (run?.evidence?.official_warnings?.data?.incidents ?? []) as ApiOfficialWarningIncident[];
  const warningCount = run?.evidence?.official_warnings?.data?.incident_count ?? warnings.length;
  const totalItems = alerts.length + pendingActions.length + warningCount + monitorTasks.length;

  return (
    <Card id="emergency-requests-panel" className={cn("flex h-full flex-col border-slate-200 shadow-sm", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">Alerts &amp; approvals</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="outline">{mode === "demo" ? "Operational" : "Live"}</Badge>
            <Badge variant="elevated">{totalItems} items</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4">
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Official warnings</div>
            <Badge className="max-w-[11rem] truncate text-[10px]" variant="outline">{warningSource}</Badge>
          </div>
          {warnings.length ? (
            warnings.map((warning) => (
              <div className="rounded-lg border border-slate-200 bg-white px-3 py-3" key={warning.guid ?? warning.title}>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-[13px] font-medium leading-4 text-slate-800">
                    <TriangleAlert className="h-4 w-4 text-orange-600" />
                    {warning.title}
                  </div>
                  <Badge variant={badgeForWarning(warning.alert_level)}>{warning.alert_level}</Badge>
                </div>
                <div className="mt-2 text-[11px] leading-4 text-slate-500">
                  {warning.location} · {warning.status} · {warning.distance_km} km
                </div>
                {warning.updated_at ? (
                  <div className="mt-1 text-[11px] text-slate-400">{formatTimestamp(warning.updated_at)}</div>
                ) : null}
              </div>
            ))
          ) : (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-3 text-[13px] leading-5 text-slate-500">
              {warningSummary ?? "No official warnings inside the monitored radius yet."}
            </div>
          )}
        </div>

        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Monitor tasks</div>
          {monitorTasks.length ? (
            monitorTasks.map((task) => (
              <div className="rounded-lg border border-slate-200 bg-white px-3 py-3" key={task.task_id}>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-[13px] font-medium leading-4 text-slate-800">
                    <Activity className="h-4 w-4 text-emerald-700" />
                    {task.region_name}
                  </div>
                  <Badge variant="muted">{task.status}</Badge>
                </div>
                <div className="mt-2 text-[11px] leading-4 text-slate-500">
                  Refreshes every {task.interval_minutes} minutes · next {formatTimestamp(task.next_check_at)}
                </div>
                {task.last_risk_score != null ? (
                  <div className="mt-1 text-[11px] text-slate-400">
                    Last score {task.last_risk_score}/100 · {task.last_risk_level}
                  </div>
                ) : null}
              </div>
            ))
          ) : (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-3 text-[13px] leading-5 text-slate-500">
              No monitor tasks yet. Ask the agent to monitor this state every 10 minutes.
            </div>
          )}
        </div>

        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Active alerts</div>
          {alerts.length ? (
            alerts.map((alert) => (
              <div className="rounded-lg border border-slate-200 bg-white px-3 py-3" key={alert.alert_id}>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-[13px] font-medium leading-4 text-slate-800">
                    <TriangleAlert className="h-4 w-4 text-red-700" />
                    {alert.region_name}
                  </div>
                  <Badge variant="severe">{alert.severity}</Badge>
                </div>
                <div className="mt-2 text-[11px] leading-4 text-slate-500">{alert.reason}</div>
              </div>
            ))
          ) : (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-3 text-[13px] leading-5 text-slate-500">
              No active alerts yet.
            </div>
          )}
        </div>

        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Pending approvals</div>
          {pendingActions.length ? (
            pendingActions.map((action) => (
              <div
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-3 text-left transition hover:border-slate-300 hover:bg-slate-50"
                key={action.action_id}
                onClick={() => {
                  setDecisionError(null);
                  setExpandedActionId((current) => (current === action.action_id ? null : action.action_id));
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setDecisionError(null);
                    setExpandedActionId((current) => (current === action.action_id ? null : action.action_id));
                  }
                }}
                role="button"
                tabIndex={0}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-[13px] font-medium leading-4 text-slate-800">
                    <ShieldAlert className="h-4 w-4 text-orange-600" />
                    {action.title}
                  </div>
                  <Badge variant="elevated">pending</Badge>
                </div>
                <div className="mt-2 text-[11px] leading-4 text-slate-500">{action.action_type}</div>
                {expandedActionId === action.action_id ? (
                  <div className="mt-3 space-y-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-3">
                    <div className="text-xs leading-5 text-slate-600">{action.draft}</div>
                    {decisionError ? <div className="text-xs text-red-700">{decisionError}</div> : null}
                    <div className="flex flex-wrap gap-2">
                      <Button
                        disabled={busyActionId === action.action_id}
                        size="sm"
                        type="button"
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleApproveAction(action);
                        }}
                      >
                        <CheckCircle2 className="mr-2 h-4 w-4" />
                        Approve
                      </Button>
                      <Button
                        disabled={busyActionId === action.action_id}
                        size="sm"
                        type="button"
                        variant="outline"
                        onClick={(event) => {
                          event.stopPropagation();
                          void handleRejectAction(action);
                        }}
                      >
                        <XCircle className="mr-2 h-4 w-4" />
                        Decline
                      </Button>
                    </div>
                  </div>
                ) : null}
              </div>
            ))
          ) : (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-3 text-[13px] leading-5 text-slate-500">
              No pending approvals yet. Draft an external action from the chatbox to populate this queue.
            </div>
          )}
        </div>

        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-[11px] leading-4 text-slate-500">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-slate-500" />
            Official warnings come from the active run evidence. Alert and approval records remain routed through the agent workflow.
          </div>
        </div>
      </CardContent>
    </Card>
  );

  async function handleApproveAction(action: ApiAction) {
    setBusyActionId(action.action_id);
    setDecisionError(null);
    try {
      const result = await approveAction(action.action_id);
      onActionsChange?.((current) => upsertAction(current, result.action));
      await downloadApprovedAdvisoryAssets(result.action, run);
      setExpandedActionId(null);
    } catch (error) {
      setDecisionError(error instanceof Error ? error.message : "Failed to approve action.");
    } finally {
      setBusyActionId(null);
    }
  }

  async function handleRejectAction(action: ApiAction) {
    setBusyActionId(action.action_id);
    setDecisionError(null);
    try {
      const result = await rejectAction(action.action_id);
      onActionsChange?.((current) => upsertAction(current, result.action));
      setExpandedActionId(null);
    } catch (error) {
      setDecisionError(error instanceof Error ? error.message : "Failed to decline action.");
    } finally {
      setBusyActionId(null);
    }
  }
}

function upsertAction(actions: ApiAction[], action: ApiAction) {
  const index = actions.findIndex((item) => item.action_id === action.action_id);
  if (index === -1) {
    return [action, ...actions];
  }
  const next = [...actions];
  next[index] = action;
  return next;
}

async function downloadApprovedAdvisoryAssets(action: ApiAction, run?: ApiRun | null) {
  const postText = buildFacebookPost(action, run);
  const text = [
    action.title,
    "",
    "Approved public advisory draft:",
    action.draft,
    "",
    "Facebook-ready post:",
    postText,
    "",
    `Approval status: ${action.status}`,
  ].join("\n");
  downloadTextFile(`${safeFilename(action.title)}.txt`, text);
  await downloadPosterPng(action, postText, run);
}

function buildFacebookPost(action: ApiAction, run?: ApiRun | null) {
  const risk = run?.risk_level && run?.risk_score != null ? `${run.risk_level} (${run.risk_score}/100)` : "current wildfire conditions";
  return `${action.draft}\n\nCurrent risk: ${risk}. Follow official emergency channels for updates.`;
}

function downloadTextFile(filename: string, text: string) {
  const blob = new Blob([text], {type: "text/plain;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

async function downloadPosterPng(action: ApiAction, postText: string, run?: ApiRun | null) {
  const canvas = document.createElement("canvas");
  canvas.width = 1080;
  canvas.height = 1080;
  const context = canvas.getContext("2d");
  if (!context) {
    return;
  }
  context.fillStyle = "#f8fafc";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#0f172a";
  context.fillRect(0, 0, canvas.width, 150);
  context.fillStyle = "#ffffff";
  context.font = "700 42px Arial";
  context.fillText("Approved Public Advisory", 60, 92);
  context.fillStyle = "#ea580c";
  context.fillRect(60, 195, 160, 42);
  context.fillStyle = "#ffffff";
  context.font = "700 24px Arial";
  context.fillText("APPROVED", 82, 225);
  context.fillStyle = "#0f172a";
  context.font = "700 38px Arial";
  wrapCanvasText(context, action.title, 60, 305, 950, 48, 2);
  context.font = "400 30px Arial";
  context.fillStyle = "#334155";
  wrapCanvasText(context, postText, 60, 430, 950, 42, 9);
  context.fillStyle = "#475569";
  context.font = "700 28px Arial";
  const risk = run?.risk_level && run?.risk_score != null ? `Risk: ${run.risk_level} ${run.risk_score}/100` : "Risk: latest approved advisory";
  context.fillText(risk, 60, 980);
  const url = canvas.toDataURL("image/png");
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${safeFilename(action.title)}-poster.png`;
  anchor.click();
}

function wrapCanvasText(
  context: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  lineHeight: number,
  maxLines: number
) {
  const words = text.split(/\s+/);
  let line = "";
  let lineCount = 0;
  for (const word of words) {
    const nextLine = line ? `${line} ${word}` : word;
    if (context.measureText(nextLine).width > maxWidth && line) {
      context.fillText(line, x, y);
      y += lineHeight;
      line = word;
      lineCount += 1;
      if (lineCount >= maxLines) {
        return;
      }
    } else {
      line = nextLine;
    }
  }
  if (line && lineCount < maxLines) {
    context.fillText(line, x, y);
  }
}

function safeFilename(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "public-advisory";
}

function badgeForWarning(alertLevel: string) {
  if (alertLevel === "Emergency Warning") return "severe" as const;
  if (alertLevel === "Watch and Act") return "elevated" as const;
  return "outline" as const;
}

function formatTimestamp(timestamp: string) {
  return new Intl.DateTimeFormat("en-AU", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  }).format(new Date(timestamp));
}
