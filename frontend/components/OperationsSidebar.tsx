"use client";

import { ActivitySquare, FileSearch, FileText, Flame, ListTree, ShieldCheck } from "lucide-react";

import { ApiRun } from "../lib/api";
import { cn } from "../lib/utils";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

export type SupportSection = "trace" | "evidence" | "reports" | "analytics";

const navItems: {
  key: SupportSection;
  label: string;
  description: string;
  icon: typeof ListTree;
}[] = [
  {
    key: "trace",
    label: "Agent Trace",
    description: "Execution steps and workflow status",
    icon: ListTree
  },
  {
    key: "evidence",
    label: "Evidence",
    description: "Hotspots, weather, warnings, Elastic MCP",
    icon: FileSearch
  },
  {
    key: "reports",
    label: "Reports",
    description: "Saved operational briefs",
    icon: FileText
  },
  {
    key: "analytics",
    label: "Risk Trend",
    description: "Primary wildfire pressure trend",
    icon: ActivitySquare
  }
];

export function OperationsSidebar({
  activeSection,
  evidenceCount = 0,
  focusedSelection,
  isOverviewLoading = false,
  onSelectSection,
  pendingApprovalCount = 0,
  reportCount = 0,
  run
}: {
  activeSection: SupportSection;
  evidenceCount?: number;
  focusedSelection?: {regionName: string; radiusKm: number} | null;
  isOverviewLoading?: boolean;
  onSelectSection: (section: SupportSection) => void;
  pendingApprovalCount?: number;
  reportCount?: number;
  run?: ApiRun | null;
}) {
  const radiusKm = run?.evidence?.region_context?.radius_km ?? focusedSelection?.radiusKm ?? 30;
  const focusLabel = run?.region_name ?? focusedSelection?.regionName ?? "Australia overview";
  const completedAt = run?.completed_at ? formatTime(run.completed_at) : null;
  const statusLabel = run ? "Active run" : isOverviewLoading ? "Loading live feed" : focusedSelection ? "Focused AOI" : "Standby";

  return (
    <div className="flex h-full flex-col gap-4">
      <Card className="border-slate-200 bg-slate-950 text-white shadow-sm">
        <CardContent className="flex items-center gap-3 p-4">
          <div className="flex h-11 w-11 items-center justify-center rounded-md border border-white/10 bg-white/10">
            <Flame className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-300">Wildfire Ops</div>
            <div className="truncate text-lg font-semibold">Console</div>
            <div className="truncate text-xs text-slate-300">{focusLabel}</div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-slate-200 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Current Watch</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
            <div className="flex items-start gap-2">
              <ShieldCheck className="mt-0.5 h-4 w-4 text-slate-700" />
              <div className="space-y-1">
                <div className="text-sm font-medium text-slate-900">{statusLabel}</div>
                <div className="text-xs leading-5 text-slate-500">{radiusKm} km operational radius around {focusLabel}.</div>
              </div>
            </div>
          </div>
          <div className="grid gap-2 text-xs text-slate-500">
            <div>{completedAt ? `Last run completed at ${completedAt}.` : "No completed analysis run in this session yet."}</div>
            <div>{pendingApprovalCount > 0 ? `${pendingApprovalCount} approvals are waiting for review.` : "No approvals are waiting for review."}</div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-slate-200 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm">Navigation</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = item.key === activeSection;
            const count = item.key === "evidence" ? evidenceCount : item.key === "reports" ? reportCount : undefined;

            return (
              <Button
                className={cn(
                  "h-auto w-full justify-start gap-3 rounded-lg px-3 py-3 text-left",
                  isActive && "border-slate-300 bg-slate-900 text-white hover:bg-slate-900 hover:text-white"
                )}
                key={item.key}
                onClick={() => onSelectSection(item.key)}
                type="button"
                variant={isActive ? "secondary" : "ghost"}
              >
                <div
                  className={cn(
                    "flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-700",
                    isActive && "border-white/10 bg-white/10 text-white"
                  )}
                >
                  <Icon className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium">{item.label}</span>
                    {count != null ? <Badge variant={isActive ? "outline" : "muted"}>{count}</Badge> : null}
                  </div>
                  <div className={cn("truncate text-xs text-slate-500", isActive && "text-slate-300")}>{item.description}</div>
                </div>
              </Button>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}

function formatTime(timestamp: string) {
  return new Intl.DateTimeFormat("en-AU", {
    hour: "numeric",
    minute: "2-digit"
  }).format(new Date(timestamp));
}
