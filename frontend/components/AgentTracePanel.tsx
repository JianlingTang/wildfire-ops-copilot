"use client";

import { CheckCircle2, CircleDashed, Clock3, TriangleAlert } from "lucide-react";

import { ApiTraceEvent } from "../lib/api";
import { Badge } from "./ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { ScrollArea } from "./ui/scroll-area";
import { cn } from "../lib/utils";

type TraceStatus = "pending" | "running" | "completed" | "failed";

type TraceItem = {
  called: string;
  did: string;
  output: string;
  status: TraceStatus;
  timestamp: string;
};

function statusMeta(status: TraceStatus) {
  switch (status) {
    case "running":
      return {
        badge: "elevated" as const,
        icon: <Clock3 className="h-4 w-4 text-orange-600" />,
        label: "running"
      };
    case "failed":
      return {
        badge: "severe" as const,
        icon: <TriangleAlert className="h-4 w-4 text-red-700" />,
        label: "failed"
      };
    case "pending":
      return {
        badge: "outline" as const,
        icon: <CircleDashed className="h-4 w-4 text-slate-400" />,
        label: "pending"
      };
    default:
      return {
        badge: "outline" as const,
        icon: <CheckCircle2 className="h-4 w-4 text-emerald-700" />,
        label: "completed"
      };
  }
}

export function AgentTracePanel({
  className,
  events = [],
  mode = "demo"
}: {
  className?: string;
  events?: ApiTraceEvent[];
  mode?: string;
}) {
  const traceItems = events.map(toTraceItem);

  return (
    <Card id="trace-panel" className={cn("border-slate-200 shadow-sm", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">Agent Plan &amp; Trace</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="outline">{mode === "demo" ? "Demo Mode" : "Live"}</Badge>
            <Badge variant="outline">{traceItems.filter((item) => item.status === "completed").length} completed</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[280px] pr-3">
          {traceItems.length ? (
            <div className="space-y-3">
              {traceItems.map((item) => {
                const meta = statusMeta(item.status);
                return (
                  <div className="rounded-lg border border-slate-200 bg-white px-3 py-3" key={`${item.timestamp}-${item.called}-${item.output}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex gap-3">
                        <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded-full bg-slate-100">{meta.icon}</div>
                        <div className="space-y-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-xs font-medium text-slate-400">{item.timestamp}</span>
                            <Badge variant={meta.badge}>{meta.label}</Badge>
                          </div>
                          <div className="text-xs text-slate-500">
                            <span className="font-medium text-slate-700">Called:</span> {item.called}
                          </div>
                          <div className="text-sm text-slate-600">
                            <span className="font-medium text-slate-700">Actions:</span> {item.did}
                          </div>
                          <div className="text-sm text-slate-600">
                            <span className="font-medium text-slate-700">Output:</span> {item.output}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-sm text-slate-500">
              No trace yet. Ask the agent to analyze the region and generate a report.
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

function toTraceItem(event: ApiTraceEvent): TraceItem {
  return {
    called: event.agent,
    did: humanizeStep(event.step),
    output: event.summary,
    status: event.status,
    timestamp: formatTime(event.timestamp)
  };
}

function humanizeStep(step: string) {
  const overrides: Record<string, string> = {
    route_chat_analysis_request: "Routed the chat-driven analysis request.",
    query_elastic_mcp_evidence: "Queried Elastic MCP evidence.",
    gather_weather_hotspots_and_exposure: "Gathered weather, hotspot, warning, and exposure inputs.",
    compute_risk_assessment: "Computed the deterministic wildfire risk assessment.",
    generate_daily_report: "Generated the daily report for the dashboard.",
    create_high_risk_alert: "Created a high-risk alert for operator review.",
    complete_without_alert: "Completed the workflow without creating an alert.",
    return_operator_summary: "Returned the operator summary to the dashboard."
  };
  return overrides[step] ?? step.replace(/_/g, " ").replace(/^\w/, (char) => char.toUpperCase()) + ".";
}

function formatTime(timestamp: string) {
  return new Intl.DateTimeFormat("en-AU", {
    hour: "numeric",
    minute: "2-digit"
  }).format(new Date(timestamp));
}
