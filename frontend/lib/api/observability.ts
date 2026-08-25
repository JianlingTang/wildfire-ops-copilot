import { getFirebaseIdToken } from "../firebaseAuth";
import { API_BASE_URL, apiHeaders } from "./client";
import type { ApiAgentEvent, ApiTraceEvent } from "./types";

export async function getRunEvents(runId: string): Promise<{events: ApiTraceEvent[]}> {
  const response = await fetch(`${API_BASE_URL}/api/runs/${runId}/events`, {headers: await apiHeaders()});
  if (!response.ok) {
    throw new Error("Failed to load run events");
  }
  return response.json();
}

export async function getRecentAgentEvents(limit = 20): Promise<{events: ApiAgentEvent[]}> {
  const params = new URLSearchParams({limit: String(limit)});
  const response = await fetch(`${API_BASE_URL}/api/agent-events/recent?${params.toString()}`, {headers: await apiHeaders()});
  if (!response.ok) {
    throw new Error("Failed to load agent activity");
  }
  return response.json();
}

export function getAgentEventsWebSocketUrl() {
  const base = new URL(API_BASE_URL);
  base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
  base.pathname = "/api/agent-events/ws";
  return base.toString();
}

// The credential travels in the first frame, not the URL: query strings are recorded in
// access logs and proxy history. Browsers cannot set headers on a WebSocket handshake,
// so the first frame is the way to keep it out of the URL.
export async function openAgentEventsSocket(): Promise<WebSocket> {
  const idToken = await getFirebaseIdToken();
  const socket = new WebSocket(getAgentEventsWebSocketUrl());
  socket.addEventListener(
    "open",
    () => {
      if (idToken) {
        socket.send(JSON.stringify({type: "auth", token: idToken}));
      }
    },
    {once: true}
  );
  return socket;
}
