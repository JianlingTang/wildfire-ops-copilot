import { getFirebaseIdToken } from "../firebaseAuth";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8001";

export class ApiRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

export async function apiRequestError(response: Response, fallbackMessage: string): Promise<ApiRequestError> {
  const payload = (await response.json().catch(() => null)) as {
    detail?: string | {message?: string};
    message?: string;
  } | null;
  const detailMessage =
    typeof payload?.detail === "string" ? payload.detail : payload?.detail?.message;
  return new ApiRequestError(detailMessage ?? payload?.message ?? fallbackMessage, response.status);
}

export async function apiHeaders(headers: HeadersInit = {}): Promise<HeadersInit> {
  const idToken = await getFirebaseIdToken();
  return idToken ? {...headers, Authorization: `Bearer ${idToken}`} : headers;
}
