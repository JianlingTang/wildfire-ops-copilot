// Backend API client, split by endpoint domain:
// - types.ts: response/request type definitions.
// - client.ts: base URL, ApiRequestError, and the shared apiHeaders()/apiRequestError() helpers.
// - chat.ts: startManualRun, sendChat.
// - hotspots.ts: getHotspotOverview, getHotspotFocus.
// - observability.ts: run events, recent agent events, the agent-events WebSocket.
// - actions.ts: alerts, actions/approvals, monitor tasks.
// Re-exported from here so every existing `from "../lib/api"` import keeps working unchanged.

export * from "./types";
export * from "./client";
export * from "./chat";
export * from "./hotspots";
export * from "./observability";
export * from "./actions";
