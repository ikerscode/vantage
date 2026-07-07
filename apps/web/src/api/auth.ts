import { useEffect } from "react";

import { useAuthStore } from "../store/authStore";
import { getApiBaseUrl } from "./client";

interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

// PLACEHOLDER(v1): fetches a token for the single hardcoded dev user from
// apps/api's dev-only auth stub. v2 replaces this with a real OIDC flow
// against self-hosted Keycloak.
async function fetchDevToken(): Promise<string> {
  const response = await fetch(`${getApiBaseUrl()}/api/auth/dev-token`, { method: "POST" });
  if (!response.ok) throw new Error("failed to fetch dev token");
  const data = (await response.json()) as TokenResponse;
  return data.access_token;
}

// SEC-01: fetched once the session token exists (this endpoint requires
// auth) — see store/authStore.ts and components/MapCanvas.tsx for where
// it's attached to outgoing tile requests.
async function fetchTilerToken(sessionToken: string): Promise<string> {
  const response = await fetch(`${getApiBaseUrl()}/api/auth/tiler-token`, {
    headers: { Authorization: `Bearer ${sessionToken}` },
  });
  if (!response.ok) throw new Error("failed to fetch tiler token");
  const data = (await response.json()) as { tilerToken: string };
  return data.tilerToken;
}

export function useDevAuthBootstrap(): void {
  const setToken = useAuthStore((s) => s.setToken);
  const setTilerToken = useAuthStore((s) => s.setTilerToken);

  useEffect(() => {
    let cancelled = false;
    fetchDevToken()
      .then((token) => {
        if (cancelled) return;
        setToken(token);
        return fetchTilerToken(token).then((tilerToken) => {
          if (!cancelled) setTilerToken(tilerToken);
        });
      })
      .catch((err: unknown) => {
        console.error("dev auth bootstrap failed", err);
      });
    return () => {
      cancelled = true;
    };
  }, [setToken, setTilerToken]);
}
