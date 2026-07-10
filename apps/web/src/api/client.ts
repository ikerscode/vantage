import { getRuntimeConfig } from "../lib/runtimeConfig";
import { useAuthStore } from "../store/authStore";

export function getApiBaseUrl(): string {
  return getRuntimeConfig().apiBaseUrl;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = useAuthStore.getState().token;
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${getApiBaseUrl()}${path}`, { ...init, headers });
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
