import { Activity, CheckCircle2, CircleDashed, Clock3, TriangleAlert, XCircle } from "lucide-react";

import type { ApiAgentEvent } from "../../lib/api";
import { labelForAgentType, shortTime } from "../../lib/operationsConsoleUtils";
import { Badge } from "../ui/badge";
import { Card, CardContent } from "../ui/card";

export function LiveAgentActivity({events}: {events: ApiAgentEvent[]}) {
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
