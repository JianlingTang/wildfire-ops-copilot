import { Database, FileSearch, Satellite, Wind } from "lucide-react";

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
            <Badge variant="outline">{mode === "demo" ? "Demo Mode" : "Live"}</Badge>
            <Badge variant="outline">{evidenceItems.length} sources</Badge>
          </div>
        </div>
        <div className="text-xs text-slate-500">Elastic MCP provides policy, playbook, historical incident, and template evidence.</div>
      </CardHeader>
      <CardContent className="grid gap-3">
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
    items.push({
      source: evidence.weather.source ?? "Weather source",
      detail: `${evidence.weather.data?.wind_gust_max ?? "--"} km/h gusts, ${evidence.weather.data?.humidity_min ?? "--"}% humidity`,
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
      detail: evidence.spatial.summary ?? "Exposure summary unavailable.",
      icon: Database
    });
  }

  return items;
}
