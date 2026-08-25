import { CheckCircle2, CircleDashed, Loader2, TriangleAlert } from "lucide-react";

import type { ApiChatMessage } from "../../lib/api";
import { Badge } from "../ui/badge";
import { RiskTrendChart, coerceRiskTrend } from "./RiskTrendChart";
import type { InlineTraceItem, InlineTraceStatus } from "./traceHelpers";
import { progressiveTraceItems, statusLabel, traceFromChatMessage } from "./traceHelpers";

export { DownloadArtifactButton } from "./DownloadArtifactButton";

export function ChatMessageBubble({message}: {message: ApiChatMessage}) {
  const isUser = message.role === "user";
  const trace = traceFromChatMessage(message);
  const riskTrend = coerceRiskTrend(message.tool_results?.risk_trend);
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={
          isUser
            ? "max-w-[86%] rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900"
            : "max-w-[92%] rounded-lg border border-slate-200 bg-slate-100 px-3 py-2 text-slate-700"
        }
      >
        <div className="whitespace-pre-wrap leading-6">{message.content}</div>
        {!isUser && riskTrend ? <RiskTrendChart trend={riskTrend} /> : null}
        {!isUser && trace.length > 0 ? (
          <details className="mt-2">
            <summary className="cursor-pointer text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
              Tools and trace
            </summary>
            <div className="mt-2">
              <InlineAgentTrace items={trace} isRunning={false} />
            </div>
          </details>
        ) : null}
      </div>
    </div>
  );
}

export function AgentWorkLog({items, tick, title}: {items: InlineTraceItem[]; tick: number; title: string}) {
  const visibleItems = progressiveTraceItems(items, tick, true);
  const activeItem = visibleItems.find((item) => item.status === "running") ?? visibleItems[visibleItems.length - 1];
  const elapsedSeconds = Math.max(1, Math.round((tick * 1200) / 1000));
  const dots = ".".repeat((tick % 3) + 1);

  return (
    <div className="max-w-[92%] overflow-hidden rounded-lg border border-sky-200 bg-white text-slate-700 shadow-sm">
      <div className="border-b border-sky-100 bg-sky-50 px-3 py-2">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <span className="relative flex h-2.5 w-2.5 shrink-0">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sky-500 opacity-50" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-sky-600" />
            </span>
            <div className="truncate text-sm font-semibold text-slate-900">{title}</div>
          </div>
          <Badge variant="elevated">{elapsedSeconds}s</Badge>
        </div>
        <div className="mt-1 font-mono text-[11px] text-slate-500">
          agent: {activeItem?.agent ?? "Main Coordinator"} {dots}
        </div>
      </div>
      <div className="space-y-2 px-3 py-3">
        {visibleItems.map((item, index) => (
          <div className="grid grid-cols-[1.25rem_1fr] gap-2 text-xs" key={`${item.agent}-${item.action}-${index}`}>
            <div className="pt-0.5">{traceIcon(item.status)}</div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-slate-800">{item.agent}</span>
                <span className="text-slate-500">{statusLabel(item.status)}</span>
              </div>
              <div className="mt-0.5 leading-5 text-slate-600">{item.action}</div>
              <div className="truncate font-mono text-[11px] text-slate-400">{item.output}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="h-1 overflow-hidden bg-slate-100">
        <div
          className="h-full rounded-r-full bg-sky-500 transition-all duration-700"
          style={{width: `${Math.min(92, 18 + tick * 9)}%`}}
        />
      </div>
    </div>
  );
}

export function InlineAgentTrace({items, isRunning, tick = 0}: {items: InlineTraceItem[]; isRunning: boolean; tick?: number}) {
  const visibleItems =
    items.length > 0
      ? items
      : [
          {
            agent: "Main Coordinator",
            action: "Standby",
            output: "Submit a focused AOI request to see agent routing and tool calls.",
            status: "pending" as const
          }
        ];
  const displayItems = progressiveTraceItems(visibleItems, tick, isRunning);

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Agent Trace</div>
        <Badge variant={isRunning ? "elevated" : "outline"}>{isRunning ? "Running" : "Live workflow"}</Badge>
      </div>
      <div className="space-y-2 p-3">
        {displayItems.map((item, index) => (
          <div
            className={
              item.status === "running"
                ? "rounded-md border border-sky-100 bg-sky-50 px-3 py-2 shadow-[0_0_0_1px_rgba(14,165,233,0.08)]"
                : "rounded-md border border-slate-100 bg-slate-50 px-3 py-2"
            }
            key={`${item.agent}-${item.action}-${index}`}
          >
            <div className="flex items-start gap-2">
              <div className="mt-0.5">{traceIcon(item.status)}</div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-800">
                  <span>{item.agent}</span>
                  <span className="font-medium text-slate-500">- {item.action}</span>
                </div>
                <div className="mt-1 text-xs leading-5 text-slate-500">
                  <span className="font-medium text-slate-700">Output:</span> {item.output}
                </div>
                {item.status === "running" ? (
                  <div className="mt-2 h-1 overflow-hidden rounded-full bg-sky-100">
                    <div className="h-full w-1/2 animate-pulse rounded-full bg-sky-500" />
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function traceIcon(status: InlineTraceStatus) {
  if (status === "running") {
    return <Loader2 className="h-4 w-4 animate-spin text-sky-700" />;
  }
  if (status === "completed") {
    return <CheckCircle2 className="h-4 w-4 text-emerald-700" />;
  }
  if (status === "failed") {
    return <TriangleAlert className="h-4 w-4 text-red-700" />;
  }
  return <CircleDashed className="h-4 w-4 text-slate-400" />;
}
