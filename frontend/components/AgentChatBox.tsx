"use client";

import { FormEvent, useDeferredValue, useEffect, useState } from "react";
import { CheckCircle2, CircleDashed, Download, Loader2, Play, Send, Sparkles, TriangleAlert } from "lucide-react";

import { ApiAoi, ApiChatMessage, ApiHotspotVisualization, ApiRiskTrend, ChatApiResult, sendChat } from "../lib/api";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

const prompts = [
  "Analyze the most active hotspot region in Australia and generate today's report.",
  "Create a monitor task for this state every 10 minutes.",
  "Why is the current risk moderate?",
  "Show the risk trend for this AOI.",
  "What changes if wind speed increases by 20%?",
  "Which area should we inspect first? Show the five most exposed roads and assets nearby.",
  "Draft a public alert for Facebook, email, and an official advisory."
];

type ChatIntent = "analysis" | "action" | "question" | "visualization" | "monitor";
type InlineTraceStatus = "pending" | "running" | "completed" | "failed";
type InlineTraceItem = {
  agent: string;
  action: string;
  output: string;
  status: InlineTraceStatus;
};

function loadingMessageForMessage(message: string, intent: ChatIntent) {
  const normalized = message.toLowerCase();
  if (/(heatmap|heat map|contour|visuali[sz]|density map)/.test(normalized)) {
    return "Generating hotspot visualization...";
  }
  if (/(monitor task|monitoring task|monitor .*every|10 minute|10-minute)/.test(normalized)) {
    return "Creating monitor task...";
  }
  if (intent === "analysis") {
    return "Running analysis...";
  }
  if (intent === "action") {
    return "Drafting action for approval...";
  }
  if (message.toLowerCase().includes("what if")) {
    return "Running what-if scenario...";
  }
  return "Getting answer...";
}

function classifyIntent(message: string) {
  const normalized = message.toLowerCase();
  if (/(heatmap|heat map|contour|visuali[sz]|density map|hotspot map)/.test(normalized)) {
    return "visualization";
  }
  if (/(monitor task|monitoring task|monitor .*every|10 minute|10-minute)/.test(normalized)) {
    return "monitor";
  }
  if (/(analy|analysis|generate today's report|generate todays report|generate a report|generate report)/.test(normalized)) {
    return "analysis";
  }
  return /(draft|email|advisory|brief|call script|task|approve)/.test(normalized) ? "action" : "question";
}

function runningTraceForIntent(intent: ChatIntent): InlineTraceItem[] {
  if (intent === "visualization") {
    return [
      {
        agent: "Main Coordinator",
        action: "Analyzing visualization request...",
        output: "Routing to hotspot visualization workflow",
        status: "running"
      },
      {
        agent: "Hotspot Density Tool",
        action: "Preparing heatmap and contour layers",
        output: "AOI hotspot cells and contour bands pending",
        status: "pending"
      }
    ];
  }
  if (intent === "monitor") {
    return [
      {
        agent: "Main Coordinator",
        action: "Analyzing monitor task request...",
        output: "Routing to monitoring scheduler",
        status: "running"
      },
      {
        agent: "Monitoring Scheduler",
        action: "Creating 10 minute risk refresh",
        output: "Alert-on-change rule pending",
        status: "pending"
      }
    ];
  }
  if (intent === "analysis") {
    return [
      {
        agent: "Main Coordinator",
        action: "Analyzing request...",
        output: "Routing to analysis workflow",
        status: "running"
      },
      {
        agent: "Tool Router",
        action: "Preparing tool calls",
        output: "Weather, hotspots, warnings, exposure, Elastic MCP",
        status: "pending"
      },
      {
        agent: "Risk + Report Agents",
        action: "Waiting for evidence",
        output: "Risk score, alert, report pending",
        status: "pending"
      }
    ];
  }
  if (intent === "action") {
    return [
      {
        agent: "Main Coordinator",
        action: "Analyzing action command...",
        output: "Routing to approval workflow",
        status: "running"
      },
      {
        agent: "Safety Boundary",
        action: "Checking external-action rules",
        output: "Direct execution blocked until approval",
        status: "pending"
      }
    ];
  }
  return [
    {
      agent: "Main Coordinator",
      action: "Analyzing question...",
      output: "Routing to analyst response",
      status: "running"
    },
    {
      agent: "Analyst Agent",
      action: "Reading focused AOI context",
      output: "Preparing operator answer",
      status: "pending"
    }
  ];
}

function completedTraceForResult(result: ChatApiResult, intent: ChatIntent): InlineTraceItem[] {
  const backendTrace = traceFromBackend(result);
  if (backendTrace.length > 0) {
    return backendTrace;
  }

  if (result.intent === "ANALYZE_AND_REPORT" || intent === "analysis") {
    const elastic = result.run?.evidence?.elastic;
    const firstEvidence = elastic?.evidence?.[0];
    return [
      {
        agent: "Main Coordinator",
        action: "Parsed request and Focus AOI",
        output: result.run?.region_name ?? "Analysis request accepted",
        status: "completed"
      },
      {
        agent: "External Data Tools",
        action: "Called hotspot, weather, warning, and exposure tools",
        output: `${result.run?.evidence?.hotspots?.data?.count_24h ?? "--"} hotspots, ${result.run?.evidence?.official_warnings?.data?.incident_count ?? 0} warnings`,
        status: "completed"
      },
      {
        agent: "Elastic MCP Tool",
        action: "Queried operational evidence",
        output: firstEvidence?.title ? `${firstEvidence.title} (${elastic?.mode ?? "unknown"} mode)` : `${elastic?.mode ?? "unknown"} mode`,
        status: elastic?.mode === "fallback" ? "failed" : "completed"
      },
      {
        agent: "Risk + Report Agents",
        action: "Computed risk and generated report",
        output: result.run?.risk_score != null ? `${result.run.risk_level} ${result.run.risk_score}/100` : "Report generated",
        status: "completed"
      }
    ];
  }
  if (result.intent === "ACTION_COMMAND" || intent === "action") {
    return [
      {
        agent: "Main Coordinator",
        action: "Detected external action command",
        output: "ACTION_COMMAND",
        status: "completed"
      },
      {
        agent: "Approval Workflow",
        action: "Created draft action and approval record",
        output: result.response?.action?.title ?? "Pending approval created",
        status: "completed"
      },
      {
        agent: "Safety Boundary",
        action: "Blocked direct external execution",
        output: result.response?.approval?.status ?? "Human approval required",
        status: "completed"
      }
    ];
  }
  return [
    {
      agent: "Main Coordinator",
      action: "Classified operational question",
      output: result.intent || "QUESTION",
      status: "completed"
    },
    {
      agent: "Analyst Agent",
      action: "Answered from run or Focus AOI context",
      output: result.response?.status ?? "success",
      status: "completed"
    }
  ];
}

function traceFromToolTrace(trace: unknown): InlineTraceItem[] {
  if (!Array.isArray(trace)) {
    return [];
  }
  return trace
    .filter((item) => item && typeof item === "object")
    .map((item): InlineTraceItem => {
      const status = String(item.status ?? "completed");
      return {
        agent: String(item.called ?? "Agent"),
        action: String(item.did ?? "Completed workflow step."),
        output: String(item.output ?? item.next_step ?? "Completed."),
        status: status === "running" || status === "failed" || status === "pending" ? status : "completed"
      };
    });
}

function traceFromBackend(result: ChatApiResult): InlineTraceItem[] {
  return traceFromToolTrace(result.response?.tool_trace);
}

export function AgentChatBox({
  activeRunId,
  defaultRegionId = "live_australia",
  selectedRegion,
  externalAnswer,
  onNeedAoiFocus,
  onResult
}: {
  activeRunId?: string;
  defaultRegionId?: string;
  selectedRegion?: {
    regionId: string;
    regionName: string;
    aoi: ApiAoi;
  } | null;
  externalAnswer?: string;
  onNeedAoiFocus?: () => void;
  onResult?: (result: ChatApiResult) => void | Promise<void>;
}) {
  const [message, setMessage] = useState(prompts[0]);
  const [answer, setAnswer] = useState("Ask the agent to analyze the region, answer a question, or draft an action.");
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [latestRunId, setLatestRunId] = useState<string | undefined>();
  const [chatMessages, setChatMessages] = useState<ApiChatMessage[]>([]);
  const [inlineTrace, setInlineTrace] = useState<InlineTraceItem[]>([]);
  const [generatedVisualization, setGeneratedVisualization] = useState<ApiHotspotVisualization | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [runningLogTick, setRunningLogTick] = useState(0);
  const deferredMessage = useDeferredValue(message);
  const intent = classifyIntent(deferredMessage);

  useEffect(() => {
    if (externalAnswer) {
      setAnswer(externalAnswer);
    }
  }, [externalAnswer]);

  useEffect(() => {
    if (!isSubmitting) {
      setRunningLogTick(0);
      return;
    }
    const timer = window.setInterval(() => {
      setRunningLogTick((current) => current + 1);
    }, 1200);
    return () => window.clearInterval(timer);
  }, [isSubmitting]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!activeRunId && !selectedRegion) {
      setAnswer("Select a state and radius, then focus the AOI before asking the agent.");
      setInlineTrace([
        {
          agent: "Main Coordinator",
          action: "Rejected request before tool calls",
          output: "Focus AOI is required",
          status: "failed"
        }
      ]);
      onNeedAoiFocus?.();
      return;
    }
    setIsSubmitting(true);
    setRunningLogTick(0);
    setAnswer(loadingMessageForMessage(message, intent));
    const optimisticUserMessage: ApiChatMessage = {
      message_id: `local-${Date.now()}`,
      conversation_id: conversationId ?? "pending",
      role: "user",
      content: message,
      intent,
      tool_trace: [],
      tool_results: {},
      run_id: activeRunId ?? latestRunId ?? null,
      region_id: selectedRegion?.regionId ?? defaultRegionId,
      created_at: new Date().toISOString()
    };
    setChatMessages((current) => [...current, optimisticUserMessage]);
    setGeneratedVisualization(null);
    setInlineTrace(runningTraceForIntent(intent));
    try {
      const result = await sendChat(message, {
        conversationId,
        runId: activeRunId ?? latestRunId,
        regionId: selectedRegion?.regionId ?? defaultRegionId,
        regionName: selectedRegion?.regionName,
        aoi: selectedRegion?.aoi
      });
      setAnswer(
        result.response?.answer ??
          result.response?.safety_note ??
          result.response?.message ??
          "Request completed."
      );
      if (result.conversation_id) {
        setConversationId(result.conversation_id);
      }
      if (result.run?.run_id) {
        setLatestRunId(result.run.run_id);
      }
      if (result.messages?.length) {
        setChatMessages(result.messages);
      } else {
        setChatMessages((current) => [
          ...current,
          {
            message_id: `assistant-${Date.now()}`,
            conversation_id: result.conversation_id ?? conversationId ?? "local",
            role: "assistant",
            content:
              result.response?.answer ??
              result.response?.safety_note ??
              result.response?.message ??
              "Request completed.",
            intent: result.intent,
            tool_trace: result.response?.tool_trace ?? [],
            tool_results: result.response?.tool_results ?? {},
            run_id: result.run?.run_id ?? activeRunId ?? latestRunId ?? null,
            region_id: selectedRegion?.regionId ?? defaultRegionId,
            created_at: new Date().toISOString()
          }
        ]);
      }
      setInlineTrace(completedTraceForResult(result, intent));
      setGeneratedVisualization(result.response?.visualization ?? null);
      await onResult?.(result);
    } catch (error) {
      setAnswer(error instanceof Error ? error.message : "Chat request failed.");
      setInlineTrace([
        {
          agent: "Main Coordinator",
          action: "Request failed",
          output: error instanceof Error ? error.message : "Chat request failed",
          status: "failed"
        }
      ]);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Card id="chat-panel" className="border-slate-200 shadow-sm">
      <CardHeader className="space-y-3 pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">Ask or command the agent</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="outline">Operational</Badge>
            <Badge variant={intent === "action" ? "elevated" : intent === "analysis" ? "muted" : "outline"}>
              {intent === "action"
                ? "Action"
                : intent === "analysis"
                  ? "Analysis"
                  : intent === "visualization"
                    ? "Visualization"
                    : intent === "monitor"
                      ? "Monitor"
                      : "Question"}
            </Badge>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {prompts.map((prompt) => (
            <Button key={prompt} size="sm" type="button" variant="outline" onClick={() => setMessage(prompt)}>
              <Sparkles className="mr-2 h-3.5 w-3.5" />
              {prompt}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <form className="space-y-3" onSubmit={onSubmit}>
          <textarea
            aria-label="Agent command input"
            className="min-h-[112px] w-full resize-none rounded-lg border border-slate-200 bg-background px-3 py-3 text-sm outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring"
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Why is the current risk moderate? What changes if wind speed increases by 20%? Which area should we inspect first?"
            value={message}
          />
          <div className="flex items-center justify-between gap-3">
            <div className="text-xs text-slate-500">
              {intent === "action" ? (
                <span className="inline-flex items-center gap-1">
                  <TriangleAlert className="h-3.5 w-3.5 text-orange-600" />
                  External actions still require approval before execution.
                </span>
              ) : intent === "analysis" ? (
                <span className="inline-flex items-center gap-1">
                  <Play className="h-3.5 w-3.5 text-slate-500" />
                  {selectedRegion || activeRunId
                    ? "Analysis runs against the focused AOI and records Elastic MCP evidence when available."
                    : "Select a state and radius first. Analysis runs against the focused AOI."}
                </span>
              ) : intent === "visualization" ? (
                <span className="inline-flex items-center gap-1">
                  <Play className="h-3.5 w-3.5 text-slate-500" />
                  Creates a downloadable heatmap, contour GeoJSON, and AI map interpretation for the focused AOI.
                </span>
              ) : intent === "monitor" ? (
                <span className="inline-flex items-center gap-1">
                  <Play className="h-3.5 w-3.5 text-slate-500" />
                  Creates a recurring 10 minute risk monitor with alert-on-change behavior.
                </span>
              ) : (
                <span className="inline-flex items-center gap-1">
                  <Play className="h-3.5 w-3.5 text-slate-500" />
                  Questions route through the existing `/api/chat` workflow.
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button disabled={isSubmitting} type="submit">
                <Send className="mr-2 h-4 w-4" />
                {isSubmitting ? "Running..." : "Send"}
              </Button>
            </div>
          </div>
        </form>

        <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-600">
          {chatMessages.length > 0 ? (
            <div className="max-h-[360px] space-y-3 overflow-y-auto pr-1">
              {chatMessages.map((item) => (
                <ChatMessageBubble key={item.message_id} message={item} />
              ))}
              {isSubmitting ? (
                <div className="flex justify-start">
                  <AgentWorkLog items={inlineTrace} tick={runningLogTick} title={loadingMessageForMessage(message, intent)} />
                </div>
              ) : null}
            </div>
          ) : (
            <div>
              {isSubmitting ? <AgentWorkLog items={inlineTrace} tick={runningLogTick} title={answer} /> : answer}
            </div>
          )}
          {generatedVisualization ? (
            <div className="overflow-hidden rounded-md border border-slate-200 bg-white">
              <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-2">
                <div>
                  <div className="font-semibold text-slate-800">Hotspot visualization</div>
                  <div className="text-xs text-slate-500">Heatmap, contour preview, and AI interpretation</div>
                </div>
                <DownloadArtifactButton
                  label="Download hotspot visualization"
                  onClick={() => downloadVisualization(generatedVisualization)}
                />
              </div>
              {generatedVisualization.preview?.data_url ? (
                <div>
                  <img
                    alt={generatedVisualization.preview.alt || "Hotspot contour map preview"}
                    className="block max-h-[420px] w-full bg-slate-100 object-contain"
                    height={generatedVisualization.preview.height}
                    loading="lazy"
                    src={generatedVisualization.preview.data_url}
                    width={generatedVisualization.preview.width}
                  />
                </div>
              ) : null}
              <div className="px-3 py-2 text-xs leading-5 text-slate-500">
                Includes the contour map preview and a downloadable interpretation bundle.
              </div>
            </div>
          ) : null}
        </div>
        <InlineAgentTrace items={inlineTrace} isRunning={isSubmitting} tick={runningLogTick} />
      </CardContent>
    </Card>
  );
}

function ChatMessageBubble({message}: {message: ApiChatMessage}) {
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

function AgentWorkLog({items, tick, title}: {items: InlineTraceItem[]; tick: number; title: string}) {
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

function RiskTrendChart({trend}: {trend: ApiRiskTrend}) {
  const points = trend.points.filter((point) => typeof point.risk_score === "number");
  if (!points.length) {
    return null;
  }
  const chart = buildRiskTrendChart(points);
  return (
    <div className="mt-3 overflow-hidden rounded-md border border-slate-200 bg-white">
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-2">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Risk Trend</div>
          <div className="mt-1 text-sm font-semibold text-slate-800">{trend.region_name}</div>
        </div>
        <DownloadArtifactButton label="Download risk trend figure" onClick={() => downloadRiskTrendPng(trend, chart)} />
      </div>
      <div className="px-3 py-3">
        <svg
          aria-label="Risk trend chart with Date x-axis and Risk Score y-axis"
          className="block h-auto w-full"
          role="img"
          viewBox={`0 0 ${chart.width} ${chart.height}`}
        >
          <rect fill="#ffffff" height={chart.height} width={chart.width} x="0" y="0" />
          {chart.yTicks.map((tick) => (
            <g key={tick.value}>
              <line stroke="#e2e8f0" strokeDasharray="5 8" x1={chart.plotLeft} x2={chart.plotRight} y1={tick.y} y2={tick.y} />
              <text fill="#64748b" fontSize="11" textAnchor="end" x={chart.plotLeft - 10} y={tick.y + 4}>
                {tick.value}
              </text>
            </g>
          ))}
          <line stroke="#94a3b8" strokeWidth="1.4" x1={chart.plotLeft} x2={chart.plotRight} y1={chart.plotBottom} y2={chart.plotBottom} />
          <line stroke="#94a3b8" strokeWidth="1.4" x1={chart.plotLeft} x2={chart.plotLeft} y1={chart.plotTop} y2={chart.plotBottom} />
          {chart.segments.map((segment) => (
            <line
              key={segment.key}
              stroke={segment.color}
              strokeDasharray={segment.dash}
              strokeLinecap="round"
              strokeWidth="3"
              x1={segment.x1}
              x2={segment.x2}
              y1={segment.y1}
              y2={segment.y2}
            />
          ))}
          {chart.points.map((point) => (
            <g key={`${point.date}-${point.type}`}>
              <circle cx={point.x} cy={point.y} fill="#ffffff" r={point.type === "current" ? 6 : 4.5} stroke={point.color} strokeWidth={point.type === "current" ? 3 : 2.4} />
            </g>
          ))}
          {chart.xLabels.map((label) => (
            <text fill="#64748b" fontSize="10" key={label.key} textAnchor="middle" transform={`rotate(-30 ${label.x} ${chart.plotBottom + 23})`} x={label.x} y={chart.plotBottom + 23}>
              {label.text}
            </text>
          ))}
          <text fill="#475569" fontSize="12" fontWeight="700" textAnchor="middle" x={(chart.plotLeft + chart.plotRight) / 2} y={chart.height - 10}>
            Date
          </text>
          <text fill="#475569" fontSize="12" fontWeight="700" textAnchor="middle" transform={`rotate(-90 15 ${(chart.plotTop + chart.plotBottom) / 2})`} x="15" y={(chart.plotTop + chart.plotBottom) / 2}>
            Risk Score
          </text>
        </svg>
      </div>
      <div className="flex flex-wrap gap-2 px-3 pb-3 text-[11px] text-slate-500">
        {points.map((point) => (
          <span className="rounded border border-slate-200 bg-slate-50 px-2 py-1" key={`${point.date}-${point.type}`} style={{borderColor: riskColor(point.risk_level)}}>
            {point.date}: {point.risk_level} {point.risk_score}/100
          </span>
        ))}
      </div>
      <div className="border-t border-slate-100 px-3 py-2 text-xs leading-5 text-slate-500">{trend.note}</div>
    </div>
  );
}

function DownloadArtifactButton({label, onClick}: {label: string; onClick: () => void}) {
  return (
    <Button
      aria-label={label}
      size="icon"
      title={label}
      type="button"
      variant="outline"
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        onClick();
      }}
    >
      <Download className="h-4 w-4" />
    </Button>
  );
}

function buildRiskTrendChart(points: ApiRiskTrend["points"]) {
  const width = 760;
  const height = 310;
  const plotLeft = 58;
  const plotRight = width - 22;
  const plotTop = 22;
  const plotBottom = height - 64;
  const plotWidth = plotRight - plotLeft;
  const plotHeight = plotBottom - plotTop;
  const scaledPoints = points.map((point, index) => {
    const x = points.length === 1 ? plotLeft + plotWidth / 2 : plotLeft + (index / (points.length - 1)) * plotWidth;
    const y = plotBottom - (Math.max(0, Math.min(100, point.risk_score)) / 100) * plotHeight;
    return {...point, x, y, color: riskColor(point.risk_level)};
  });
  const segments = scaledPoints.slice(1).map((point, index) => {
    const previous = scaledPoints[index];
    return {
      key: `${previous.date}-${point.date}`,
      x1: previous.x,
      y1: previous.y,
      x2: point.x,
      y2: point.y,
      color: point.color,
      dash: point.type === "forecast" ? "8 6" : point.type === "historical" ? "1 0" : "1 0"
    };
  });
  const yTicks = [0, 25, 50, 75, 100].map((value) => ({
    value,
    y: plotBottom - (value / 100) * plotHeight
  }));
  const xLabels = scaledPoints
    .filter((_, index) => index % 2 === 0 || index === scaledPoints.length - 1)
    .map((point) => ({
      key: `${point.date}-${point.type}`,
      text: shortDateLabel(point.date),
      x: point.x
    }));
  return {height, plotBottom, plotLeft, plotRight, plotTop, points: scaledPoints, segments, width, xLabels, yTicks};
}

function riskColor(level: string) {
  if (level === "EXTREME") return "#b91c1c";
  if (level === "HIGH") return "#b45309";
  if (level === "MODERATE") return "#ca8a04";
  return "#15803d";
}

function shortDateLabel(value: string) {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-AU", {day: "2-digit", month: "short"}).format(date);
}

function downloadRiskTrendPng(trend: ApiRiskTrend, chart: ReturnType<typeof buildRiskTrendChart>) {
  const svg = riskTrendSvgMarkup(chart);
  const image = new Image();
  const url = URL.createObjectURL(new Blob([svg], {type: "image/svg+xml;charset=utf-8"}));
  image.onload = () => {
    const canvas = document.createElement("canvas");
    canvas.width = chart.width * 2;
    canvas.height = chart.height * 2;
    const context = canvas.getContext("2d");
    if (!context) {
      URL.revokeObjectURL(url);
      return;
    }
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.scale(2, 2);
    context.drawImage(image, 0, 0);
    URL.revokeObjectURL(url);
    downloadDataUrl(canvas.toDataURL("image/png"), trend.downloads?.png_filename ?? "risk-trend.png");
  };
  image.onerror = () => URL.revokeObjectURL(url);
  image.src = url;
}

function coerceRiskTrend(value: unknown): ApiRiskTrend | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const trend = value as ApiRiskTrend;
  return Array.isArray(trend.points) ? trend : null;
}

function traceFromChatMessage(message: ApiChatMessage): InlineTraceItem[] {
  return traceFromToolTrace(message.tool_trace);
}

function downloadVisualization(visualization: ApiHotspotVisualization) {
  if (visualization.preview?.data_url) {
    downloadDataUrl(visualization.preview.data_url, visualization.downloads.png_filename ?? "hotspot-contour-map.png");
  }
  const interpretation = visualization.downloads.txt_content ?? [
    visualization.interpretation.summary,
    visualization.interpretation.recommendation,
    visualization.interpretation.caveat
  ].join("\n\n");
  downloadBlob(new Blob([interpretation], {type: "text/plain;charset=utf-8"}), visualization.downloads.txt_filename ?? "hotspot-interpretation.txt");
}

function riskTrendSvgMarkup(chart: ReturnType<typeof buildRiskTrendChart>) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${chart.width}" height="${chart.height}" viewBox="0 0 ${chart.width} ${chart.height}">
<rect fill="#ffffff" height="${chart.height}" width="${chart.width}" x="0" y="0" />
${chart.yTicks.map((tick) => `<g><line stroke="#e2e8f0" stroke-dasharray="5 8" x1="${chart.plotLeft}" x2="${chart.plotRight}" y1="${tick.y}" y2="${tick.y}" /><text fill="#64748b" font-size="11" text-anchor="end" x="${chart.plotLeft - 10}" y="${tick.y + 4}">${tick.value}</text></g>`).join("")}
<line stroke="#94a3b8" stroke-width="1.4" x1="${chart.plotLeft}" x2="${chart.plotRight}" y1="${chart.plotBottom}" y2="${chart.plotBottom}" />
<line stroke="#94a3b8" stroke-width="1.4" x1="${chart.plotLeft}" x2="${chart.plotLeft}" y1="${chart.plotTop}" y2="${chart.plotBottom}" />
${chart.segments.map((segment) => `<line stroke="${segment.color}" stroke-dasharray="${segment.dash}" stroke-linecap="round" stroke-width="3" x1="${segment.x1}" x2="${segment.x2}" y1="${segment.y1}" y2="${segment.y2}" />`).join("")}
${chart.points.map((point) => `<circle cx="${point.x}" cy="${point.y}" fill="#ffffff" r="${point.type === "current" ? 6 : 4.5}" stroke="${point.color}" stroke-width="${point.type === "current" ? 3 : 2.4}" />`).join("")}
${chart.xLabels.map((label) => `<text fill="#64748b" font-size="10" text-anchor="middle" transform="rotate(-30 ${label.x} ${chart.plotBottom + 23})" x="${label.x}" y="${chart.plotBottom + 23}">${escapeXml(label.text)}</text>`).join("")}
<text fill="#475569" font-size="12" font-weight="700" text-anchor="middle" x="${(chart.plotLeft + chart.plotRight) / 2}" y="${chart.height - 10}">Date</text>
<text fill="#475569" font-size="12" font-weight="700" text-anchor="middle" transform="rotate(-90 15 ${(chart.plotTop + chart.plotBottom) / 2})" x="15" y="${(chart.plotTop + chart.plotBottom) / 2}">Risk Score</text>
</svg>`;
}

function escapeXml(value: string) {
  return value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

function downloadDataUrl(dataUrl: string, filename: string) {
  const [meta, encoded] = dataUrl.split(",");
  const mime = meta.match(/data:(.*?);base64/)?.[1] ?? "application/octet-stream";
  const binary = window.atob(encoded ?? "");
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  downloadBlob(new Blob([bytes], {type: mime}), filename);
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function InlineAgentTrace({items, isRunning, tick = 0}: {items: InlineTraceItem[]; isRunning: boolean; tick?: number}) {
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

function progressiveTraceItems(items: InlineTraceItem[], tick: number, isRunning: boolean): InlineTraceItem[] {
  if (!isRunning) {
    return items;
  }
  const activeIndex = Math.min(items.length - 1, Math.floor(tick / 2));
  return items.map((item, index) => {
    if (item.status === "failed") {
      return item;
    }
    if (index < activeIndex) {
      return {...item, status: "completed"};
    }
    if (index === activeIndex) {
      return {...item, status: "running"};
    }
    return {...item, status: "pending"};
  });
}

function statusLabel(status: InlineTraceStatus) {
  if (status === "running") {
    return "running";
  }
  if (status === "completed") {
    return "done";
  }
  if (status === "failed") {
    return "failed";
  }
  return "queued";
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
