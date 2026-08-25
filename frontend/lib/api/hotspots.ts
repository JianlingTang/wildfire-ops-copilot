import { getFirebaseUserEmail } from "../firebaseAuth";
import { API_BASE_URL, ApiRequestError, apiHeaders } from "./client";
import type { ApiHotspotFocus, ApiHotspotOverview } from "./types";

export async function getHotspotOverview(): Promise<ApiHotspotOverview> {
  const response = await fetch(`${API_BASE_URL}/api/hotspots/overview`, {cache: "no-store", headers: await apiHeaders()});
  return parseHotspotResponse<ApiHotspotOverview>(response, "Failed to load hotspot overview");
}

export async function getHotspotFocus(state: string, radiusKm: number): Promise<ApiHotspotFocus> {
  const params = new URLSearchParams({state, radius_km: String(radiusKm)});
  const response = await fetch(`${API_BASE_URL}/api/hotspots/focus?${params.toString()}`, {cache: "no-store", headers: await apiHeaders()});
  return parseHotspotResponse<ApiHotspotFocus>(response, "Failed to load hotspot focus");
}

async function parseHotspotResponse<T extends {status: string; message?: string; data: unknown}>(
  response: Response,
  fallbackMessage: string
): Promise<T> {
  const payload = (await response.json().catch(() => null)) as T | null;
  if (response.status === 403) {
    const email = getFirebaseUserEmail();
    throw new ApiRequestError(
      [
        email ? `Signed in as ${email}.` : "Signed in account is not authorized.",
        "This account is not authorized for this demo.",
        "Please use the approved operator account."
      ].join(" "),
      response.status
    );
  }
  if (response.status === 401) {
    throw new ApiRequestError("Please sign in with an approved Google account for this demo.", response.status);
  }
  if (!response.ok || payload?.status !== "success" || !payload.data) {
    throw new ApiRequestError(payload?.message ?? fallbackMessage, response.status);
  }
  return payload;
}
