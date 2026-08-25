import { API_BASE_URL, apiHeaders, apiRequestError } from "./client";
import type { ChatApiResult, ChatRequestOptions } from "./types";

export async function startManualRun() {
  const response = await fetch(`${API_BASE_URL}/api/runs/manual`, {
    method: "POST",
    headers: await apiHeaders({"Content-Type": "application/json"}),
    body: JSON.stringify({region_id: "live_australia", region_name: "Australia Live Hotspot AOI"})
  });
  if (!response.ok) {
    throw await apiRequestError(response, "Manual run failed");
  }
  return response.json();
}

export async function sendChat(
  message: string,
  options: ChatRequestOptions = {}
): Promise<ChatApiResult> {
  const startedAt = nowMs();
  const {
    conversationId,
    runId,
    regionId = "live_australia",
    regionName,
    aoi
  } = options;
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: await apiHeaders({"Content-Type": "application/json"}),
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      run_id: runId,
      region_id: regionId,
      region_name: regionName,
      aoi
    })
  });
  if (!response.ok) {
    throw await apiRequestError(response, "Chat request failed");
  }
  const payload = await response.json();
  return {
    ...payload,
    client_timing: {
      ...(payload.client_timing ?? {}),
      chat_api_fetch_ms: roundMs(nowMs() - startedAt)
    }
  };
}

function nowMs() {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

function roundMs(value: number) {
  return Math.round(value * 100) / 100;
}
