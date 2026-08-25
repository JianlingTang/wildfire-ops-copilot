import type { ApiAgentEvent } from "./api";

export function upsertById<T extends Record<string, any>, K extends keyof T>(items: T[], item: T, key: K) {
  const existingIndex = items.findIndex((current) => current[key] === item[key]);
  if (existingIndex === -1) {
    return [item, ...items];
  }

  const next = [...items];
  next[existingIndex] = item;
  return next;
}

export function mergeById<T extends Record<string, any>, K extends keyof T>(current: T[], incoming: T[], key: K) {
  return incoming.reduce((items, item) => upsertById(items, item, key), current);
}

export async function timedClientCall<T>(name: string, call: () => Promise<T>): Promise<T> {
  const startedAt = nowMs();
  try {
    return await call();
  } finally {
    console.info("[chat timing] frontend segment", {name, duration_ms: roundMs(nowMs() - startedAt)});
  }
}

export function nowMs() {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

export function roundMs(value: number) {
  return Math.round(value * 100) / 100;
}

export function upsertEvent(events: ApiAgentEvent[]) {
  const seen = new Map<string, ApiAgentEvent>();
  for (const event of events) {
    seen.set(event.event_id, event);
  }
  return [...seen.values()].sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp));
}

export function labelForAgentType(agentType: string) {
  const labels: Record<string, string> = {
    coordinator: "Coordinator",
    analysis: "Analysis",
    elastic: "Elastic",
    risk: "Risk Engine",
    report: "Report Agent",
    approval: "Approval",
    visualization: "Visualization",
    monitor: "Monitor"
  };
  return labels[agentType] ?? agentType;
}

export function shortTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--:--";
  }
  return new Intl.DateTimeFormat("en-AU", {hour: "2-digit", minute: "2-digit", second: "2-digit"}).format(date);
}

export function buildEvidenceSourceCount(evidence?: Record<string, any> | null) {
  if (!evidence) {
    return 0;
  }
  return ["hotspots", "weather", "official_warnings", "spatial", "elastic"].reduce(
    (count, key) => (evidence[key] ? count + 1 : count),
    0
  );
}

export function coerceCenter(center?: [number, number] | number[]) {
  if (!center || center.length !== 2) {
    return null;
  }
  const [lat, lon] = center;
  return Number.isFinite(lat) && Number.isFinite(lon) ? ([lat, lon] as [number, number]) : null;
}
