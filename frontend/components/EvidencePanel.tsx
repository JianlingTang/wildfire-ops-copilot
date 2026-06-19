import { CheckCircle2, Cloud, Database, FileSearch, Flame, Satellite, Wind } from "lucide-react";

import { cn } from "../lib/utils";
import { Badge } from "./ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

export function EvidencePanel({
  className,
  evidence,
  mode = "demo"
}: {
  className?: string;
  evidence?: Record<string, any> | null;
  mode?: string;
}) {
  const evidenceItems = buildEvidenceItems(evidence);

  return (
    <Card className={cn("border-slate-200 shadow-sm", className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">Evidence Panel</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="outline">{mode === "demo" ? "Operational" : "Live"}</Badge>
            <Badge variant="outline">{evidenceItems.length} sources</Badge>
          </div>
        </div>
        <div className="text-xs text-slate-500">Elastic MCP provides policy, playbook, historical incident, and template evidence.</div>
      </CardHeader>
      <CardContent className="grid gap-3">
        <TechProof evidence={evidence} />
        {evidenceItems.length ? (
          evidenceItems.map((item) => (
            <Card key={item.source}>
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  <div className="rounded-md bg-muted p-2">
                    <item.icon className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="text-sm font-medium">{item.source}</div>
                    <div className="mt-1 text-xs text-muted-foreground">{item.detail}</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        ) : (
          <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-sm text-slate-500">
            No evidence loaded yet. The first analysis command will attach hotspot, weather, Elastic MCP, and exposure sources.
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function buildEvidenceItems(evidence?: Record<string, any> | null) {
  if (!evidence) {
    return [];
  }

  const items = [];
  if (evidence.hotspots) {
    items.push({
      source: evidence.hotspots.source ?? "Hotspot source",
      detail: `${evidence.hotspots.data?.count_24h ?? 0} recent hotspots`,
      icon: Satellite
    });
  }
  if (evidence.weather) {
    const weatherData = evidence.weather.data ?? {};
    items.push({
      source: evidence.weather.source ?? "Weather source",
      detail:
        evidence.weather.status === "error"
          ? evidence.weather.message ?? "Weather evidence unavailable from live provider."
          : `${weatherData.wind_gust_max ?? "--"} km/h gusts, ${weatherData.humidity_min ?? "--"}% humidity`,
      icon: Wind
    });
  }
  if (evidence.elastic) {
    items.push({
      source: evidence.elastic.evidence?.[0]?.source ?? "Elastic MCP",
      detail: evidence.elastic.evidence?.[0]?.summary ?? "Elastic MCP evidence will appear here.",
      icon: FileSearch
    });
  }
  if (evidence.spatial) {
    items.push({
      source: evidence.spatial.source ?? "Spatial exposure",
      detail:
        evidence.spatial.status === "error"
          ? evidence.spatial.message ?? "Spatial exposure unavailable from live provider."
          : evidence.spatial.summary ?? "Exposure summary unavailable.",
      icon: Database
    });
  }

  return items;
}

function TechProof({evidence}: {evidence?: Record<string, any> | null}) {
  const elasticDocs = Array.isArray(evidence?.elastic?.evidence) ? evidence?.elastic?.evidence : [];
  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">Tech proof</div>
            <div className="mt-1 text-xs text-muted-foreground">Runtime technologies used by this workflow.</div>
          </div>
          <Badge variant={evidence?.elastic?.mode === "live" ? "muted" : "outline"}>
            Elastic {evidence?.elastic?.mode ?? "pending"}
          </Badge>
        </div>
        <div className="grid gap-2 text-xs text-slate-600 sm:grid-cols-2">
          <ProofItem icon={Flame} label="Gemini" value="ADK coordinator" />
          <ProofItem icon={Cloud} label="Google Cloud" value="Cloud Run + Vertex AI" />
          <ProofItem icon={FileSearch} label="Elastic MCP" value={evidence?.elastic?.tool_name ?? "search_wildfire_ops_knowledge"} />
          <ProofItem icon={CheckCircle2} label="Safety" value="Human approval boundary" />
        </div>
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Elastic citations</div>
          {elasticDocs.length ? (
            <div className="mt-2 space-y-2">
              {elasticDocs.slice(0, 5).map((doc: any, index: number) => (
                <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2" key={doc.evidence_id ?? index}>
                  <div className="text-xs font-medium text-slate-800">{doc.title ?? "Elastic evidence"}</div>
                  <div className="mt-1 text-[11px] leading-4 text-slate-500">{doc.summary ?? doc.source}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-2 rounded-md border border-dashed border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
              Run analysis to list Elastic MCP files retrieved for this AOI.
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function ProofItem({icon: Icon, label, value}: {icon: typeof Flame; label: string; value: string}) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2">
      <Icon className="h-4 w-4 text-slate-500" />
      <div>
        <div className="font-medium text-slate-800">{label}</div>
        <div className="text-[11px] text-slate-500">{value}</div>
      </div>
    </div>
  );
}
