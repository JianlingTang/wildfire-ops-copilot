import type { ApiChatMessage, ChatApiResult } from "../../lib/api";

export type ChatIntent = "analysis" | "action" | "question" | "visualization" | "monitor";
export type InlineTraceStatus = "pending" | "running" | "completed" | "failed";
export type InlineTraceItem = {
  agent: string;
  action: string;
  output: string;
  status: InlineTraceStatus;
};

export function loadingMessageForMessage(message: string, intent: ChatIntent) {
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

export function classifyIntent(message: string) {
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

export function runningTraceForIntent(intent: ChatIntent): InlineTraceItem[] {
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

export function completedTraceForResult(result: ChatApiResult, intent: ChatIntent): InlineTraceItem[] {
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

export function traceFromToolTrace(trace: unknown): InlineTraceItem[] {
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

export function traceFromBackend(result: ChatApiResult): InlineTraceItem[] {
  return traceFromToolTrace(result.response?.tool_trace);
}

export function traceFromChatMessage(message: ApiChatMessage): InlineTraceItem[] {
  return traceFromToolTrace(message.tool_trace);
}

export function progressiveTraceItems(items: InlineTraceItem[], tick: number, isRunning: boolean): InlineTraceItem[] {
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

export function statusLabel(status: InlineTraceStatus) {
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
