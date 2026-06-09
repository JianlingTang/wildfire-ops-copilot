import { Activity, FileText, ShieldAlert, TriangleAlert } from "lucide-react";

import { ApiAction, ApiAlert, ApiMonitorTask, ApiOfficialWarningIncident, ApiRun } from "../lib/api";
import { cn } from "../lib/utils";
import { Badge } from "./ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

export function EmergencyRequestPanel({
  actions = [],
  alerts = [],
  monitorTasks = [],
  run,
  className,
  mode = "demo"
}: {
  actions?: ApiAction[];
  alerts?: ApiAlert[];
  monitorTasks?: ApiMonitorTask[];
  run?: ApiRun | null;
  className?: string;
  mode?: string;
}) {
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
            <Badge variant="outline">{mode === "demo" ? "Demo Mode" : "Live"}</Badge>
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
              <div className="rounded-lg border border-slate-200 bg-white px-3 py-3" key={action.action_id}>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-[13px] font-medium leading-4 text-slate-800">
                    <ShieldAlert className="h-4 w-4 text-orange-600" />
                    {action.title}
                  </div>
                  <Badge variant="elevated">pending</Badge>
                </div>
                <div className="mt-2 text-[11px] leading-4 text-slate-500">{action.action_type}</div>
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
            Official warnings come from the active run evidence. Alert and approval records remain routed through the demo agent workflow.
          </div>
        </div>
      </CardContent>
    </Card>
  );
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
