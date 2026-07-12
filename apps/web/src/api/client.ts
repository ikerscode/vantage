import { getRuntimeConfig } from "../lib/runtimeConfig";
import { useAuthStore } from "../store/authStore";

export function getApiBaseUrl(): string {
  return getRuntimeConfig().apiBaseUrl;
}

export class ApiError extends Error {
  // Short, stable code shown in the error toast so a user can report exactly
  // what failed: VG-<httpStatus> for a server response (e.g. VG-401, VG-500),
  // VG-TIMEOUT when the request exceeded REQUEST_TIMEOUT_MS, VG-NET for a
  // network/CORS failure with no response at all.
  readonly code: string;
  constructor(
    public status: number,
    message: string,
    code?: string,
  ) {
    super(message);
    this.code = code ?? (status > 0 ? `VG-${status}` : "VG-NET");
  }
}

// BRIEF v2, found for real on a live install: a server-side request that
// never completed (an unbounded imagery search) left the UI waiting forever
// with zero feedback — "infinite loading" with nothing in the error toasts,
// because a hang never rejects. The server side is fixed too (the search is
// now capped and timed out), but no single endpoint fix prevents the next
// hang — this bound turns ANY future one into a visible, toastable error.
// Generous on purpose: the slowest legitimate request (a wide imagery
// search) completes in ~15s; nothing legitimate takes a minute. Only API
// calls go through here — tile fetches and the SSE stream don't use
// apiFetch, so neither is affected.
const REQUEST_TIMEOUT_MS = 60_000;

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = useAuthStore.getState().token;
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers,
      signal: init.signal ?? AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "TimeoutError") {
      throw new ApiError(0, `request to ${path} timed out after ${REQUEST_TIMEOUT_MS / 1000}s`, "VG-TIMEOUT");
    }
    throw err;
  }
  if (!response.ok) {
    const raw = await response.text();
    // FastAPI's default error shape is {"detail": "..."} — surface that
    // directly rather than a raw JSON blob when a toast displays it (see
    // store/toastStore.ts's pushErrorToast, wired app-wide in main.tsx).
    let message = raw || response.statusText;
    try {
      const parsed = JSON.parse(raw) as { detail?: unknown };
      if (typeof parsed.detail === "string") message = parsed.detail;
    } catch {
      // not JSON — use the raw text as-is
    }
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
