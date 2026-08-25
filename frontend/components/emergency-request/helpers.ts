import type { ApiAction } from "../../lib/api";

export function upsertAction(actions: ApiAction[], action: ApiAction) {
  const index = actions.findIndex((item) => item.action_id === action.action_id);
  if (index === -1) {
    return [action, ...actions];
  }
  const next = [...actions];
  next[index] = action;
  return next;
}

export function badgeForWarning(alertLevel: string) {
  if (alertLevel === "Emergency Warning") return "severe" as const;
  if (alertLevel === "Watch and Act") return "elevated" as const;
  return "outline" as const;
}

export function formatTimestamp(timestamp: string) {
  return new Intl.DateTimeFormat("en-AU", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  }).format(new Date(timestamp));
}
