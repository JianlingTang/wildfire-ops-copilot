"use client";

import { CloudRain, ShieldAlert, ThermometerSun, Wind } from "lucide-react";

import { ApiRun } from "../lib/api";
import { OperatorMetricCard } from "./OperatorMetricCard";

type OperationalOverviewProps = {
  onSelectDetail: (detail: "alerts" | "approvals" | "evidence" | "trace") => void;
  alertCount?: number;
  hotspotCountOverride?: number;
  pendingApprovalCount?: number;
  run?: ApiRun | null;
  showHeading?: boolean;
};

export function OperationalOverview({
  alertCount = 0,
  hotspotCountOverride = 0,
  onSelectDetail,
  pendingApprovalCount = 0,
  run,
  showHeading = true
}: OperationalOverviewProps) {
  const weather = run?.evidence?.weather?.data ?? {};
  const hotspots = run?.evidence?.hotspots?.data ?? {};
  const hasRun = Boolean(run);
  const riskLevel = run?.risk_level ?? "STANDBY";
  const isSevere = riskLevel === "HIGH" || riskLevel === "EXTREME";
  const topDriver = run?.risk_assessment?.drivers?.[0]?.factor ?? "Run analysis from chat to populate evidence.";
  const hotspotCount = hasRun ? (hotspots.count_24h ?? 0) : hotspotCountOverride;

  return (
    <section className="space-y-3" id="operational-overview">
      {showHeading ? (
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Operational Overview</h2>
            <p className="text-xs text-slate-500">Key wildfire operating numbers for the active run.</p>
          </div>
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <OperatorMetricCard
          badge="Score"
          detail={hasRun ? "Open trace context for score drivers and execution details." : "Run a chat-driven analysis to populate the score."}
          label="Current Risk Score"
          onClick={() => onSelectDetail("trace")}
          subtitle="Deterministic wildfire score"
          value={run?.risk_score != null ? String(run.risk_score) : "--"}
          valueSuffix={run?.risk_score != null ? "/ 100" : undefined}
        />
        <OperatorMetricCard
          badge="Severity"
          badgeVariant={isSevere ? "severe" : "default"}
          detail={hasRun ? "Current severity band with low-to-high color reference." : "Severity updates after a chat-driven analysis run."}
          label="Risk Level"
          onClick={() => onSelectDetail("trace")}
          subtitle="Operational severity"
          tone={isSevere ? "severe" : "default"}
          value={riskLevel}
          withColorBar
        />
        <OperatorMetricCard
          badge="Alerting"
          badgeVariant={alertCount > 0 ? "severe" : "default"}
          detail={alertCount > 0 ? "Active alerts were created from the latest chat-driven analysis run." : "No active alerts yet."}
          label="Active Alerts"
          onClick={() => onSelectDetail("alerts")}
          subtitle="Open alert inbox"
          tone={alertCount > 0 ? "severe" : "default"}
          value={String(alertCount)}
        />
        <OperatorMetricCard
          badge="Monitoring"
          badgeVariant="elevated"
          detail={hasRun ? "Recent hotspot detections remain inside the monitored radius." : "Nationwide hotspot counts stay live before analysis runs."}
          label="New Hotspots"
          onClick={() => onSelectDetail("evidence")}
          subtitle={hasRun ? "Recent detections" : "Live 24h detections"}
          tone="elevated"
          value={String(hotspotCount)}
        />
        <OperatorMetricCard
          badge="Forecast"
          detail={
            <span className="inline-flex items-center gap-1">
              <Wind className="h-3.5 w-3.5" />
              {hasRun ? `${topDriver} remains a key scoring driver.` : "Forecast evidence appears after the analysis run."}
            </span>
          }
          label="Wind Gust Max"
          onClick={() => onSelectDetail("evidence")}
          subtitle="Forecast maximum"
          value={weather.wind_gust_max != null ? String(weather.wind_gust_max) : "--"}
          valueSuffix={weather.wind_gust_max != null ? "km/h" : undefined}
        />
        <OperatorMetricCard
          badge="Forecast"
          detail={
            <span className="inline-flex items-center gap-1">
              <ThermometerSun className="h-3.5 w-3.5" />
              {hasRun ? "Low humidity is contributing to current spread potential." : "Humidity evidence appears after the analysis run."}
            </span>
          }
          label="Humidity Min"
          onClick={() => onSelectDetail("evidence")}
          subtitle="Forecast minimum"
          value={weather.humidity_min != null ? String(weather.humidity_min) : "--"}
          valueSuffix={weather.humidity_min != null ? "%" : undefined}
        />
        <OperatorMetricCard
          badge="Forecast"
          detail={
            <span className="inline-flex items-center gap-1">
              <CloudRain className="h-3.5 w-3.5" />
              {hasRun ? "Rainfall remains below the higher-confidence relief band." : "Rainfall evidence appears after the analysis run."}
            </span>
          }
          label="Rainfall 7d"
          onClick={() => onSelectDetail("evidence")}
          subtitle="Accumulated rainfall"
          value={weather.rainfall_7d != null ? String(weather.rainfall_7d) : "--"}
          valueSuffix={weather.rainfall_7d != null ? "mm" : undefined}
        />
        <OperatorMetricCard
          badge="Approval"
          badgeVariant={pendingApprovalCount > 0 ? "elevated" : "default"}
          detail={
            <span className="inline-flex items-center gap-1">
              <ShieldAlert className="h-3.5 w-3.5" />
              {pendingApprovalCount > 0 ? "External drafts remain blocked until approved." : "No pending approvals are waiting."}
            </span>
          }
          label="Pending Approvals"
          onClick={() => onSelectDetail("approvals")}
          subtitle="Human action queue"
          tone={pendingApprovalCount > 0 ? "elevated" : "default"}
          value={String(pendingApprovalCount)}
        />
      </div>
    </section>
  );
}
