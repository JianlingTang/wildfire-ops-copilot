"use client";

import { Filter, Globe2, MapPinned } from "lucide-react";

import { ApiHotspotStateSummary } from "../lib/api";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

export function AoiSelectionToolbar({
  appliedSelection,
  draftRadiusKm,
  draftState,
  isFocusing,
  isLoading,
  onApply,
  onDraftRadiusChange,
  onDraftStateChange,
  onReset,
  states
}: {
  appliedSelection?: {regionName: string; radiusKm: number} | null;
  draftRadiusKm: number;
  draftState: string;
  isFocusing: boolean;
  isLoading: boolean;
  onApply: () => void;
  onDraftRadiusChange: (value: number) => void;
  onDraftStateChange: (value: string) => void;
  onReset: () => void;
  states: ApiHotspotStateSummary[];
}) {
  const selectedState = states.find((state) => state.state === draftState) ?? null;
  const radiusOptions = selectedState?.radius_options_km ?? [30, 50, 100, 200];

  return (
    <Card className="border-slate-200 shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <CardTitle className="text-base">Australia hotspot overview</CardTitle>
            <div className="text-xs text-slate-500">
              Default view stays at nationwide hotspots. Focus a state AOI when you want to analyze a narrower area.
            </div>
          </div>
          <div className="hidden items-center gap-2 text-xs text-slate-500 sm:flex">
            <Globe2 className="h-3.5 w-3.5" />
            Nationwide view
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_180px_auto_auto]">
          <label className="grid gap-1 text-xs font-medium text-slate-600">
            State
            <select
              className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400"
              disabled={isLoading || states.length === 0}
              onChange={(event) => onDraftStateChange(event.target.value)}
              value={draftState}
            >
              {states.map((state) => (
                <option key={state.state} value={state.state}>
                  {state.label} ({state.count_24h})
                </option>
              ))}
            </select>
          </label>

          <label className="grid gap-1 text-xs font-medium text-slate-600">
            Radius
            <select
              className="h-10 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400"
              disabled={isLoading}
              onChange={(event) => onDraftRadiusChange(Number(event.target.value))}
              value={String(draftRadiusKm)}
            >
              {radiusOptions.map((radiusKm) => (
                <option key={radiusKm} value={radiusKm}>
                  {radiusKm} km
                </option>
              ))}
            </select>
          </label>

          <Button disabled={isLoading || !selectedState} onClick={onApply} type="button">
            <MapPinned className="mr-2 h-4 w-4" />
            {isFocusing ? "Focusing..." : "Focus AOI"}
          </Button>

          <Button disabled={isLoading} onClick={onReset} type="button" variant="outline">
            <Filter className="mr-2 h-4 w-4" />
            Show Australia
          </Button>
        </div>

        <div className="text-xs text-slate-500">
          {isFocusing
            ? `Focusing ${selectedState?.label ?? "selected state"} on its most active hotspot cluster.`
            : appliedSelection
            ? `${appliedSelection.regionName} is focused with a ${appliedSelection.radiusKm} km radius. Chat analysis will use this AOI.`
            : selectedState
              ? `Showing nationwide hotspots. Focus AOI will jump to the densest hotspot cluster in ${selectedState.label}.`
              : "Loading nationwide hotspots and available state AOIs."}
        </div>
      </CardContent>
    </Card>
  );
}
