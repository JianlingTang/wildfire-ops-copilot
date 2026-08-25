import { useEffect, useState } from "react";

import { ApiAgentEvent, getRecentAgentEvents, openAgentEventsSocket } from "../../lib/api";
import { upsertEvent } from "../../lib/operationsConsoleUtils";

export function useAgentEventsFeed() {
  const [agentEvents, setAgentEvents] = useState<ApiAgentEvent[]>([]);

  useEffect(() => {
    let cancelled = false;
    let socket: WebSocket | null = null;
    let pollTimer: number | null = null;

    async function loadRecent() {
      try {
        const payload = await getRecentAgentEvents(20);
        if (!cancelled) {
          setAgentEvents(payload.events);
        }
      } catch {
        // Activity stream is observability-only; do not interrupt the operations console.
      }
    }

    void loadRecent();

    async function connectStream() {
      try {
        socket = await openAgentEventsSocket();
        socket.onmessage = (event) => {
          try {
            const parsed = JSON.parse(event.data);
            // The server opens with a {"type":"ready"} frame; only agent events carry an id.
            if (parsed?.event_id) {
              setAgentEvents((current) => upsertEvent([...current, parsed as ApiAgentEvent]).slice(-20));
            }
          } catch {
            // Ignore malformed observability events.
          }
        };
        socket.onerror = () => {
          if (!pollTimer) {
            pollTimer = window.setInterval(loadRecent, 2500);
          }
        };
        socket.onclose = () => {
          if (!cancelled && !pollTimer) {
            pollTimer = window.setInterval(loadRecent, 2500);
          }
        };
      } catch {
        pollTimer = window.setInterval(loadRecent, 2500);
      }
    }

    void connectStream();

    return () => {
      cancelled = true;
      socket?.close();
      if (pollTimer) {
        window.clearInterval(pollTimer);
      }
    };
  }, []);

  return agentEvents;
}
