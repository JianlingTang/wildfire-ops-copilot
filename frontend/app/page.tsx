"use client";

import { Flame, TriangleAlert, X } from "lucide-react";

import { AgentChatBox } from "../components/AgentChatBox";
import { AuthGate } from "../components/AuthGate";
import { AoiSelectionToolbar } from "../components/AoiSelectionToolbar";
import { EvidencePanel } from "../components/EvidencePanel";
import { EmergencyRequestPanel } from "../components/EmergencyRequestPanel";
import { MapDashboard } from "../components/MapDashboard";
import { MobileSidebarSheet } from "../components/MobileSidebarSheet";
import { CompactSummaryStrip } from "../components/operations-console/CompactSummaryStrip";
import { LiveAgentActivity } from "../components/operations-console/LiveAgentActivity";
import { useAgentEventsFeed } from "../components/operations-console/useAgentEventsFeed";
import { useOperationsData } from "../components/operations-console/useOperationsData";
import { OperationsSidebar, SupportSection } from "../components/OperationsSidebar";
import { ReportCenter } from "../components/ReportCenter";
import { Badge } from "../components/ui/badge";
import { Card, CardContent } from "../components/ui/card";

const supportMeta: Record<SupportSection, {eyebrow: string; title: string; description: string}> = {
  evidence: {
    eyebrow: "Support panel",
    title: "Evidence Sources",
    description: "Review live inputs and Elastic MCP evidence attached to the current run."
  },
  reports: {
    eyebrow: "Support panel",
    title: "Reports",
    description: "Open the saved operational briefs generated from the active analysis."
  }
};

export default function Home() {
  return (
    <AuthGate>
      <OperationsConsole />
    </AuthGate>
  );
}

function OperationsConsole() {
  const mode = "demo";
  const agentEvents = useAgentEventsFeed();
  const data = useOperationsData();
  const {refs} = data;
  const support = supportMeta[data.activeSupport];
  const focusAoi = data.focusedSelection
    ? {regionName: data.focusedSelection.regionName, radiusKm: data.focusedSelection.radiusKm}
    : null;

  return (
    <main className="min-h-screen bg-background">
      {data.toastMessage ? (
        <div
          className="fixed right-4 top-20 z-[70] w-[min(calc(100vw-2rem),24rem)] rounded-lg border border-orange-200 bg-orange-50 px-4 py-3 text-orange-950 shadow-lg"
          role="alert"
        >
          <div className="flex items-start gap-3">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-orange-700" />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold">AOI focus required</div>
              <div className="mt-1 text-xs leading-5 text-orange-900">{data.toastMessage}</div>
            </div>
            <button
              aria-label="Dismiss notification"
              className="rounded p-1 text-orange-700 transition hover:bg-orange-100"
              onClick={() => data.setToastMessage(null)}
              type="button"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      ) : null}

      <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-background/95 backdrop-blur">
        <div className="flex h-16 items-center justify-between gap-4 px-4 lg:px-6">
          <div className="flex items-center gap-3">
            <MobileSidebarSheet>
              <OperationsSidebar
                activeSection={data.activeSupport}
                evidenceCount={data.evidenceCount}
                focusedSelection={focusAoi}
                isOverviewLoading={data.overviewLoading}
                onSelectSection={data.openSupport}
                pendingApprovalCount={data.pendingApprovalCount}
                reportCount={data.reports.length}
                run={data.activeRun}
              />
            </MobileSidebarSheet>

            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-md border border-slate-300 bg-white">
                <Flame className="h-5 w-5 text-slate-800" />
              </div>
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Wildfire Ops</div>
                <h1 className="text-lg font-semibold leading-6 text-slate-950 sm:text-2xl">Emergency Operations Console</h1>
              </div>
            </div>
          </div>

          <div className="hidden items-center gap-2 md:flex">
            <Badge variant="outline">Operational</Badge>
            <Badge variant="muted">{data.focusDescriptor}</Badge>
            <Badge variant="elevated">{data.currentHotspotCount} hotspots</Badge>
            <Badge variant="outline">{data.warningCount} warnings</Badge>
            <Badge variant="outline">{data.pendingApprovalCount} approvals</Badge>
          </div>
        </div>
      </header>

      {data.accessNotice ? (
        <section className="border-b border-red-200 bg-red-50 px-4 py-3 text-red-950 lg:px-6" role="alert">
          <div className="flex max-w-5xl items-start gap-3">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-red-700" />
            <div className="min-w-0">
              <div className="text-sm font-semibold">Demo access not authorized</div>
              <div className="mt-1 text-sm leading-5 text-red-900">{data.accessNotice}</div>
            </div>
          </div>
        </section>
      ) : null}

      <div className="p-4 lg:p-5">
        <section className="grid grid-cols-1 gap-4 xl:grid-cols-[232px_minmax(0,1fr)]">
          <aside className="order-2 xl:order-1">
            <OperationsSidebar
              activeSection={data.activeSupport}
              evidenceCount={data.evidenceCount}
              focusedSelection={focusAoi}
              isOverviewLoading={data.overviewLoading}
              onSelectSection={data.openSupport}
              pendingApprovalCount={data.pendingApprovalCount}
              reportCount={data.reports.length}
              run={data.activeRun}
            />
          </aside>

          <div className="order-1 grid gap-4 xl:order-2">
            <div ref={refs.aoiRef}>
              <AoiSelectionToolbar
                appliedSelection={focusAoi}
                draftRadiusKm={data.draftRadiusKm}
                draftState={data.draftState}
                isFocusing={data.focusLoading}
                isLoading={data.overviewLoading || data.focusLoading}
                onApply={data.handleApplyFocus}
                onDraftRadiusChange={data.setDraftRadiusKm}
                onDraftStateChange={data.setDraftState}
                onReset={data.handleResetOverview}
                states={data.stateOptions}
              />
            </div>

            <CompactSummaryStrip
              hotspotCount={data.currentHotspotCount}
              pendingApprovalCount={data.pendingApprovalCount}
              riskLevel={data.activeRun?.risk_level ?? "STANDBY"}
              riskScore={data.activeRun?.risk_score}
              warningCount={data.warningCount}
            />

            <div className="min-h-[460px]">
              <MapDashboard
                overview={data.overview}
                run={data.activeRun}
                selectedFocus={data.focusedSelection}
                visualization={data.visualization}
              />
            </div>

            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.08fr)_380px]">
              <AgentChatBox
                activeRunId={data.activeRun?.run_id}
                defaultRegionId={data.activeRun?.region_id ?? "live_australia"}
                externalAnswer={data.latestAnswer}
                onNeedAoiFocus={data.requestAoiFocus}
                onResult={data.handleChatResult}
                selectedRegion={
                  !data.focusedSelection
                    ? null
                    : {
                        regionId: data.focusedSelection.regionId,
                        regionName: data.focusedSelection.regionName,
                        aoi: {
                          center: data.focusedSelection.center,
                          radius_km: data.focusedSelection.radiusKm
                        }
                      }
                }
              />

              <div className="grid gap-4" ref={refs.queueRef}>
                <LiveAgentActivity events={agentEvents} />
                <EmergencyRequestPanel
                  actions={data.actions}
                  alerts={data.alerts}
                  className="h-full"
                  mode={mode}
                  monitorTasks={data.monitorTasks}
                  onActionsChange={data.setActions}
                  run={data.activeRun}
                />
              </div>
            </div>

            <div className="grid gap-4" ref={refs.supportRef}>
              <Card className="border-slate-200 shadow-sm">
                <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-end sm:justify-between">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">{support.eyebrow}</div>
                    <div className="mt-1 text-xl font-semibold text-slate-950">{support.title}</div>
                    <div className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">{support.description}</div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="muted">{data.focusDescriptor}</Badge>
                    <Badge variant="outline">{mode === "demo" ? "Agent workflow" : "Live workflow"}</Badge>
                  </div>
                </CardContent>
              </Card>

              {data.activeSupport === "evidence" ? <EvidencePanel evidence={data.activeRun?.evidence} mode={mode} /> : null}
              {data.activeSupport === "reports" ? <ReportCenter mode={mode} reports={data.reports} /> : null}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
