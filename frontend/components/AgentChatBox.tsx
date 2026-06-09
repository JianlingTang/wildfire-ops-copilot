"use client";

import { FormEvent, useDeferredValue, useEffect, useState } from "react";
import { CheckCircle2, CircleDashed, Clock3, Play, Send, Sparkles, TriangleAlert } from "lucide-react";

import { ApiAoi, ChatApiResult, sendChat } from "../lib/api";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

const prompts = [
  "Analyze the most active hotspot region in Australia and generate today's report.",
  "What changed since yesterday?",
  "What if wind increases by 20%?",
  "Which area should we inspect first?",
  "Draft a public advisory for this alert."
];

type ChatIntent = "analysis" | "action" | "question";
type InlineTraceStatus = "pending" | "running" | "completed" | "failed";
type InlineTraceItem = {
  agent: string;
  action: string;
  output: string;
  status: InlineTraceStatus;
};

function loadingMessageForMessage(message: string, intent: "analysis" | "action" | "question") {
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
  if (/(analy|analysis|generate today's report|generate todays report|generate a report|generate report)/.test(normalized)) {
    return "analysis";
  }
  return /(draft|email|advisory|brief|call script|task|approve)/.test(normalized) ? "action" : "question";
}

function runningTraceForIntent(intent: ChatIntent): InlineTraceItem[] {
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

function traceFromBackend(result: ChatApiResult): InlineTraceItem[] {
  const trace = result.response?.tool_trace;
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

export function AgentChatBox({
  activeRunId,
  defaultRegionId = "live_australia",
  selectedRegion,
  externalAnswer,
  onNeedAoiFocus,
  onResult,
  onShowTrace
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
  onShowTrace?: () => void;
}) {
  const [message, setMessage] = useState(prompts[0]);
  const [answer, setAnswer] = useState("Ask the agent to analyze the region, answer a question, or draft an action.");
  const [inlineTrace, setInlineTrace] = useState<InlineTraceItem[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const deferredMessage = useDeferredValue(message);
  const intent = classifyIntent(deferredMessage);

  useEffect(() => {
    if (externalAnswer) {
      setAnswer(externalAnswer);
    }
  }, [externalAnswer]);

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
    setAnswer(loadingMessageForMessage(message, intent));
    setInlineTrace(runningTraceForIntent(intent));
    try {
      const result = await sendChat(message, {
        runId: activeRunId,
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
      setInlineTrace(completedTraceForResult(result, intent));
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
            <Badge variant="outline">Demo Mode</Badge>
            <Badge variant={intent === "action" ? "elevated" : intent === "analysis" ? "muted" : "outline"}>
              {intent === "action" ? "Action" : intent === "analysis" ? "Analysis" : "Question"}
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
            placeholder="What changed since yesterday? What if wind increases by 20%? Which area should we inspect first? Draft a public advisory for this alert."
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
                    ? "Demo mode runs analysis against the focused AOI and records Elastic MCP evidence when available."
                    : "Select a state and radius first. Analysis runs against the focused AOI."}
                </span>
              ) : (
                <span className="inline-flex items-center gap-1">
                  <Play className="h-3.5 w-3.5 text-slate-500" />
                  Questions route through the existing `/api/chat` workflow.
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {onShowTrace ? (
                <Button type="button" variant="outline" onClick={onShowTrace}>
                  <Play className="mr-2 h-4 w-4" />
                  Show agent trace &amp; activities
                </Button>
              ) : null}
              <Button disabled={isSubmitting} type="submit">
                <Send className="mr-2 h-4 w-4" />
                {isSubmitting ? "Running..." : "Send"}
              </Button>
            </div>
          </div>
        </form>

        <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-600">{answer}</div>
        <InlineAgentTrace items={inlineTrace} isRunning={isSubmitting} />
      </CardContent>
    </Card>
  );
}

function InlineAgentTrace({items, isRunning}: {items: InlineTraceItem[]; isRunning: boolean}) {
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

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
        <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Agent Trace</div>
        <Badge variant={isRunning ? "elevated" : "outline"}>{isRunning ? "Running" : "Live workflow"}</Badge>
      </div>
      <div className="space-y-2 p-3">
        {visibleItems.map((item, index) => (
          <div
            className={item.status === "running" ? "rounded-md border border-sky-100 bg-sky-50 px-3 py-2" : "rounded-md border border-slate-100 bg-slate-50 px-3 py-2"}
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
    return <Clock3 className="h-4 w-4 text-sky-700" />;
  }
  if (status === "completed") {
    return <CheckCircle2 className="h-4 w-4 text-emerald-700" />;
  }
  if (status === "failed") {
    return <TriangleAlert className="h-4 w-4 text-red-700" />;
  }
  return <CircleDashed className="h-4 w-4 text-slate-400" />;
}
