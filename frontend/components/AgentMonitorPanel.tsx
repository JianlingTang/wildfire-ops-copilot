import { Activity, ShieldCheck } from "lucide-react";

import { ApiRun } from "../lib/api";
import { Badge } from "./ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

export function AgentMonitorPanel({
  focusedSelection,
  isOverviewLoading = false,
  run,
}: {
  focusedSelection?: {
    regionName: string;
    radiusKm: number;
  } | null;
  isOverviewLoading?: boolean;
  run?: ApiRun | null;
}) {
  const completedAt = run?.completed_at ? formatTime(run.completed_at) : null;
  const radiusKm = run?.evidence?.region_context?.radius_km ?? focusedSelection?.radiusKm ?? 30;
  const selectionMode = run?.evidence?.region_context?.selection_mode;
  const statusLabel = run ? "Active" : isOverviewLoading ? "Loading" : focusedSelection ? "Focused" : "Standby";
  const statusClasses = run
    ? "border-emerald-200 bg-emerald-50 text-emerald-900"
    : isOverviewLoading
      ? "border-amber-200 bg-amber-50 text-amber-900"
      : focusedSelection
        ? "border-sky-200 bg-sky-50 text-sky-900"
      : "border-slate-200 bg-slate-50 text-slate-700";
  const detailClasses = run
    ? "text-emerald-800"
    : isOverviewLoading
      ? "text-amber-800"
      : focusedSelection
        ? "text-sky-800"
        : "text-slate-500";

  return (
    <Card id="monitor-panel" className="border-slate-200 shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">Agents Monitor Status</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="outline">Operational</Badge>
            <Badge variant="outline">{statusLabel}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className={`rounded-lg border px-3 py-3 ${statusClasses}`}>
          <div className="flex items-start gap-2">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="space-y-1">
              <div className="font-medium">{radiusKm} km operational radius</div>
              <div className={`text-xs ${detailClasses}`}>
                {completedAt
                  ? `Chat-driven risk analysis completed at ${completedAt}.`
                  : isOverviewLoading
                    ? "Loading the nationwide hotspot overview and cached state AOIs."
                    : focusedSelection
                      ? `${focusedSelection.regionName} is focused. Run a chat-driven analysis for this AOI.`
                  : "Awaiting the first chat-driven analysis request."}
              </div>
            </div>
          </div>
        </div>
        <div className="grid gap-2 text-xs text-slate-500">
          <div className="flex items-center gap-2">
            <Activity className="h-3.5 w-3.5" />
            {run
              ? selectionMode?.includes("auto")
                ? "Monitoring remains live for the auto-selected hotspot AOI."
                : "Monitoring remains live for the current AOI."
              : focusedSelection
                ? "The dashboard is pinned to the selected state focus."
                : "Australia-wide hotspot overview is active."}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function formatTime(timestamp: string) {
  return new Intl.DateTimeFormat("en-AU", {
    hour: "numeric",
    minute: "2-digit"
  }).format(new Date(timestamp));
}
