import { useState } from "react";
import { CheckCircle2, ShieldAlert, XCircle } from "lucide-react";

import { ApiAction, ApiRun, approveAction, rejectAction } from "../../lib/api";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { downloadApprovedAdvisoryAssets } from "./advisoryDownload";
import { upsertAction } from "./helpers";

export function PendingApprovalsList({
  actions,
  run,
  onActionsChange
}: {
  actions: ApiAction[];
  run?: ApiRun | null;
  onActionsChange?: (actions: ApiAction[] | ((current: ApiAction[]) => ApiAction[])) => void;
}) {
  const [expandedActionId, setExpandedActionId] = useState<string | null>(null);
  const [busyActionId, setBusyActionId] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);

  async function handleApproveAction(action: ApiAction) {
    setBusyActionId(action.action_id);
    setDecisionError(null);
    try {
      const result = await approveAction(action.action_id);
      onActionsChange?.((current) => upsertAction(current, result.action));
      await downloadApprovedAdvisoryAssets(result.action, run);
      setExpandedActionId(null);
    } catch (error) {
      setDecisionError(error instanceof Error ? error.message : "Failed to approve action.");
    } finally {
      setBusyActionId(null);
    }
  }

  async function handleRejectAction(action: ApiAction) {
    setBusyActionId(action.action_id);
    setDecisionError(null);
    try {
      const result = await rejectAction(action.action_id);
      onActionsChange?.((current) => upsertAction(current, result.action));
      setExpandedActionId(null);
    } catch (error) {
      setDecisionError(error instanceof Error ? error.message : "Failed to decline action.");
    } finally {
      setBusyActionId(null);
    }
  }

  if (!actions.length) {
    return (
      <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-3 text-[13px] leading-5 text-slate-500">
        No pending approvals yet. Draft an external action from the chatbox to populate this queue.
      </div>
    );
  }

  return (
    <>
      {actions.map((action) => (
        <div
          className="w-full rounded-lg border border-slate-200 bg-white px-3 py-3 text-left transition hover:border-slate-300 hover:bg-slate-50"
          key={action.action_id}
          onClick={() => {
            setDecisionError(null);
            setExpandedActionId((current) => (current === action.action_id ? null : action.action_id));
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              setDecisionError(null);
              setExpandedActionId((current) => (current === action.action_id ? null : action.action_id));
            }
          }}
          role="button"
          tabIndex={0}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-[13px] font-medium leading-4 text-slate-800">
              <ShieldAlert className="h-4 w-4 text-orange-600" />
              {action.title}
            </div>
            <Badge variant="elevated">pending</Badge>
          </div>
          <div className="mt-2 text-[11px] leading-4 text-slate-500">{action.action_type}</div>
          {expandedActionId === action.action_id ? (
            <div className="mt-3 space-y-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-3">
              <div className="text-xs leading-5 text-slate-600">{action.draft}</div>
              {decisionError ? <div className="text-xs text-red-700">{decisionError}</div> : null}
              <div className="flex flex-wrap gap-2">
                <Button
                  disabled={busyActionId === action.action_id}
                  size="sm"
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    void handleApproveAction(action);
                  }}
                >
                  <CheckCircle2 className="mr-2 h-4 w-4" />
                  Approve
                </Button>
                <Button
                  disabled={busyActionId === action.action_id}
                  size="sm"
                  type="button"
                  variant="outline"
                  onClick={(event) => {
                    event.stopPropagation();
                    void handleRejectAction(action);
                  }}
                >
                  <XCircle className="mr-2 h-4 w-4" />
                  Decline
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      ))}
    </>
  );
}
