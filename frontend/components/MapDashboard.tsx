"use client";

import dynamic from "next/dynamic";
import { Layers, LocateFixed } from "lucide-react";

import { ApiHotspot, ApiHotspotOverview, ApiOfficialWarningIncident, ApiRun } from "../lib/api";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";

const LeafletMap = dynamic(() => import("./leaflet/LeafletMap"), {ssr: false});

export function MapDashboard({
  overview,
  run,
  selectedFocus
}: {
  overview?: ApiHotspotOverview | null;
  run?: ApiRun | null;
  selectedFocus?: {
    state: string;
    regionName: string;
    center: [number, number];
    radiusKm: number;
    hotspotCount: number;
    hotspots: ApiHotspot[];
    source: string;
    statewideHotspotCount: number;
  } | null;
}) {
  const mapState = buildMapState(run, overview, selectedFocus);

  return (
    <Card className="relative min-h-[420px] overflow-hidden xl:h-full xl:min-h-0">
      <div className="absolute left-4 top-4 z-[500] flex flex-wrap items-center gap-2">
        <Badge variant="muted">AOI Boundary</Badge>
        <Badge variant={mapState.zoneVariant}>{mapState.zoneLabel}</Badge>
        <Badge variant="elevated">{mapState.hotspotCount} hotspots</Badge>
        <Badge variant="outline">{mapState.warningCount} warnings</Badge>
      </div>
      <div className="absolute right-4 top-4 z-[500] flex gap-2">
        <Button size="sm" variant="secondary" type="button">
          <Layers className="mr-2 h-4 w-4" />
          Layers
        </Button>
        <Button size="icon" variant="secondary" type="button" aria-label="Center map">
          <LocateFixed className="h-4 w-4" />
        </Button>
      </div>
      <div className="h-[420px] xl:h-full">
        <LeafletMap
          center={mapState.center}
          hotspots={mapState.hotspots}
          radiusKm={mapState.radiusKm}
          riskLevel={mapState.riskLevel}
          warnings={mapState.warnings}
        />
      </div>
      <div className="absolute bottom-4 left-4 z-[500] grid gap-1 rounded-lg border bg-card/95 p-3 text-xs shadow-sm backdrop-blur">
        <div className="font-semibold">{mapState.regionName} operational area</div>
        <div className="text-muted-foreground">{mapState.summaryLine}</div>
        <div className="text-muted-foreground">{mapState.sourceLine}</div>
      </div>
    </Card>
  );
}

function buildMapState(
  run: ApiRun | null | undefined,
  overview: ApiHotspotOverview | null | undefined,
  selectedFocus:
    | {
        state: string;
        regionName: string;
        center: [number, number];
        radiusKm: number;
        hotspotCount: number;
        hotspots: ApiHotspot[];
        source: string;
        statewideHotspotCount: number;
      }
    | null
    | undefined
) {
  if (run) {
    const hotspots = run.evidence?.hotspots?.data?.hotspots?.filter(isValidHotspot) ?? [];
    const warnings = run.evidence?.official_warnings?.data?.incidents?.filter(isMappableWarning) ?? [];
    const regionContext = run.evidence?.region_context;
    const radiusKm = regionContext?.radius_km ?? 30;
    const center = coerceCenter(regionContext?.center);
    return {
      center,
      hotspotCount: run.evidence?.hotspots?.data?.count_24h ?? hotspots.length,
      hotspots,
      radiusKm,
      regionName: run.region_name,
      riskLevel: run.risk_level,
      sourceLine: `${run.evidence?.hotspots?.source ?? "Hotspot feed"} · ${run.evidence?.official_warnings?.source ?? "Official warning feed"}`,
      summaryLine: `${run.evidence?.hotspots?.data?.count_24h ?? hotspots.length} hotspots · ${run.evidence?.official_warnings?.data?.incident_count ?? warnings.length} warnings · ${radiusKm} km radius`,
      warningCount: run.evidence?.official_warnings?.data?.incident_count ?? warnings.length,
      warnings,
      zoneLabel: `${run.risk_level ?? "Standby"} zone`,
      zoneVariant: "severe" as const,
    };
  }

  const overviewHotspots = overview?.data?.hotspots?.filter(isValidHotspot) ?? [];
  const sourceLine = selectedFocus
    ? `${selectedFocus.source} · Run analysis to load official warnings`
    : `${overview?.source ?? "Hotspot feed"} · Select a state and radius to focus an AOI`;

  return {
    center: selectedFocus?.center,
    hotspotCount: selectedFocus?.hotspotCount ?? overview?.data?.total_count_24h ?? overviewHotspots.length,
    hotspots: selectedFocus?.hotspots ?? overviewHotspots,
    radiusKm: selectedFocus?.radiusKm ?? 30,
    regionName: selectedFocus?.regionName ?? "Australia hotspot overview",
    riskLevel: null,
    sourceLine,
    summaryLine: selectedFocus
      ? `${selectedFocus.hotspotCount} hotspots in focus AOI · ${selectedFocus.statewideHotspotCount} statewide · ${selectedFocus.radiusKm} km radius`
      : `${overview?.data?.total_count_24h ?? 0} hotspots · ${overview?.data?.display_hotspot_count ?? overviewHotspots.length} points rendered nationwide`,
    warningCount: 0,
    warnings: [],
    zoneLabel: selectedFocus ? `${selectedFocus.state} focus` : "Australia overview",
    zoneVariant: "outline" as const,
  };
}

function isValidHotspot(hotspot: ApiHotspot | null | undefined): hotspot is ApiHotspot {
  return Boolean(hotspot && Number.isFinite(hotspot.lat) && Number.isFinite(hotspot.lon));
}

function isMappableWarning(
  warning: ApiOfficialWarningIncident | null | undefined
): warning is ApiOfficialWarningIncident & {lat: number; lon: number} {
  return Boolean(warning && Number.isFinite(warning.lat) && Number.isFinite(warning.lon));
}

function coerceCenter(center?: [number, number] | number[]) {
  if (!center || center.length !== 2) {
    return undefined;
  }
  const [lat, lon] = center;
  return Number.isFinite(lat) && Number.isFinite(lon) ? ([lat, lon] as [number, number]) : undefined;
}
