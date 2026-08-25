import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiAction,
  ApiAlert,
  ApiHotspotFocus,
  ApiHotspotOverview,
  ApiHotspotVisualization,
  ApiMonitorTask,
  ApiReport,
  ApiRun,
  ChatApiResult,
  getHotspotFocus,
  getHotspotOverview
} from "../../lib/api";
import { buildEvidenceSourceCount } from "../../lib/operationsConsoleUtils";
import type { SupportSection } from "../OperationsSidebar";
import {
  applyChatResultToState,
  applyLoadError,
  defaultDraftState,
  focusSelectionFrom,
  refreshAlertsActionsAndMonitorTasks
} from "./operationsDataHelpers";

export type FocusSelection = {
  state: string;
  label: string;
  regionId: string;
  regionName: string;
  center: [number, number];
  radiusKm: number;
  hotspotCount: number;
  hotspots: {
    lat: number;
    lon: number;
    state?: string | null;
    confidence: string;
    detected_at: string;
    power?: number | null;
    satellite?: string | null;
    sensor?: string | null;
  }[];
  source: string;
  statewideHotspotCount: number;
};

export function useOperationsData() {
  const aoiRef = useRef<HTMLDivElement | null>(null);
  const queueRef = useRef<HTMLDivElement | null>(null);
  const supportRef = useRef<HTMLDivElement | null>(null);

  const [activeSupport, setActiveSupport] = useState<SupportSection>("evidence");
  const [activeRun, setActiveRun] = useState<ApiRun | null>(null);
  const [reports, setReports] = useState<ApiReport[]>([]);
  const [alerts, setAlerts] = useState<ApiAlert[]>([]);
  const [actions, setActions] = useState<ApiAction[]>([]);
  const [monitorTasks, setMonitorTasks] = useState<ApiMonitorTask[]>([]);
  const [visualization, setVisualization] = useState<ApiHotspotVisualization | null>(null);
  const [latestAnswer, setLatestAnswer] = useState<string | undefined>(undefined);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [focusLoading, setFocusLoading] = useState(false);
  const [overview, setOverview] = useState<ApiHotspotOverview | null>(null);
  const [focus, setFocus] = useState<ApiHotspotFocus | null>(null);
  const [draftState, setDraftState] = useState("");
  const [draftRadiusKm, setDraftRadiusKm] = useState(50);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [accessNotice, setAccessNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadOverview() {
      setOverviewLoading(true);
      try {
        const payload = await getHotspotOverview();
        if (cancelled) {
          return;
        }
        setOverview(payload);
        setAccessNotice(null);
        setDraftState((current) => current || defaultDraftState(payload));
      } catch (error) {
        if (!cancelled) {
          applyLoadError(error, setAccessNotice, setLatestAnswer, "Failed to load hotspot overview.");
        }
      } finally {
        if (!cancelled) {
          setOverviewLoading(false);
        }
      }
    }

    void loadOverview();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!toastMessage) {
      return;
    }
    const timeout = window.setTimeout(() => setToastMessage(null), 4200);
    return () => window.clearTimeout(timeout);
  }, [toastMessage]);

  const stateOptions = useMemo(
    () =>
      [...(overview?.data?.states ?? [])].sort(
        (left, right) => right.count_24h - left.count_24h || left.label.localeCompare(right.label)
      ),
    [overview]
  );
  const draftStateSummary = useMemo(
    () => stateOptions.find((state) => state.state === draftState) ?? null,
    [draftState, stateOptions]
  );
  const focusedSelection = useMemo(() => focusSelectionFrom(focus), [focus]);

  const currentHotspotCount =
    activeRun?.evidence?.hotspots?.data?.count_24h ?? focusedSelection?.hotspotCount ?? overview?.data?.total_count_24h ?? 0;
  const warningCount = activeRun?.evidence?.official_warnings?.data?.incident_count ?? 0;
  const pendingApprovalCount = useMemo(() => actions.filter((action) => action.status === "pending_approval").length, [actions]);
  const evidenceCount = useMemo(() => buildEvidenceSourceCount(activeRun?.evidence), [activeRun?.evidence]);
  const focusDescriptor = activeRun?.region_name ?? focusedSelection?.regionName ?? "Australia hotspot overview";

  const clearOperationalState = useCallback(() => {
    setActiveRun(null);
    setReports([]);
    setAlerts([]);
    setActions([]);
    setMonitorTasks([]);
    setVisualization(null);
  }, []);

  const openSupport = useCallback((section: SupportSection) => {
    setActiveSupport(section);
    window.requestAnimationFrame(() => {
      supportRef.current?.scrollIntoView({behavior: "smooth", block: "start"});
    });
  }, []);

  const openQueue = useCallback(() => {
    queueRef.current?.scrollIntoView({behavior: "smooth", block: "start"});
  }, []);

  const requestAoiFocus = useCallback(() => {
    setToastMessage("Select a state and radius, then click Focus AOI before asking the agent.");
    aoiRef.current?.scrollIntoView({behavior: "smooth", block: "start"});
    setLatestAnswer("Select a state and radius, then click Focus AOI before asking the agent.");
  }, []);

  const handleChatResult = useCallback(
    (result: ChatApiResult) => {
      applyChatResultToState(result, {setLatestAnswer, setActiveRun, setReports, setAlerts, setVisualization, setMonitorTasks, openQueue});
      if (result.intent === "ANALYZE_AND_REPORT" || result.intent === "ACTION_COMMAND" || result.intent === "MONITOR_TASK") {
        void refreshAlertsActionsAndMonitorTasks(result, setAlerts, setActions, setMonitorTasks);
      }
    },
    [openQueue]
  );

  const handleApplyFocus = useCallback(() => {
    if (!draftStateSummary || focusLoading) {
      return;
    }

    clearOperationalState();
    setFocusLoading(true);
    setFocus(null);
    void (async () => {
      try {
        const payload = await getHotspotFocus(draftStateSummary.state, draftRadiusKm);
        setFocus(payload);
        setAccessNotice(null);
        setLatestAnswer(
          `${payload.data.label} is focused on its most active hotspot cluster at ${payload.data.radius_km} km. Run analysis from the AI chatbox to populate risk, warnings, and reports for this AOI.`
        );
      } catch (error) {
        applyLoadError(error, setAccessNotice, setLatestAnswer, "Failed to focus the AOI.");
      } finally {
        setFocusLoading(false);
      }
    })();
  }, [clearOperationalState, draftRadiusKm, draftStateSummary, focusLoading]);

  const handleResetOverview = useCallback(() => {
    setFocus(null);
    clearOperationalState();
    setLatestAnswer("Showing nationwide hotspots. Select a state and radius, then focus the AOI before running analysis.");
  }, [clearOperationalState]);

  return {
    refs: {aoiRef, queueRef, supportRef},
    activeSupport,
    activeRun,
    reports,
    alerts,
    actions,
    setActions,
    monitorTasks,
    visualization,
    latestAnswer,
    overviewLoading,
    focusLoading,
    overview,
    draftState,
    setDraftState,
    draftRadiusKm,
    setDraftRadiusKm,
    toastMessage,
    setToastMessage,
    accessNotice,
    stateOptions,
    focusedSelection,
    currentHotspotCount,
    warningCount,
    pendingApprovalCount,
    evidenceCount,
    focusDescriptor,
    openSupport,
    openQueue,
    requestAoiFocus,
    handleChatResult,
    handleApplyFocus,
    handleResetOverview
  };
}
