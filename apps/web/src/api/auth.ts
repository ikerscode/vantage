import { useEffect } from "react";

import { useAuthStore } from "../store/authStore";
import { API_BASE_URL } from "./client";

interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

// PLACEHOLDER(v1): fetches a token for the single hardcoded dev user from
// apps/api's dev-only auth stub. v2 replaces this with a real OIDC flow
// against self-hosted Keycloak.
async function fetchDevToken(): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/api/auth/dev-token`, { method: "POST" });
  if (!response.ok) throw new Error("failed to fetch dev token");
  const data = (await response.json()) as TokenResponse;
  return data.access_token;
}

export function useDevAuthBootstrap(): void {
  const setToken = useAuthStore((s) => s.setToken);

  useEffect(() => {
    let cancelled = false;
    fetchDevToken()
      .then((token) => {
        if (!cancelled) setToken(token);
      })
      .catch((err: unknown) => {
        console.error("dev auth bootstrap failed", err);
      });
    return () => {
      cancelled = true;
    };
  }, [setToken]);
}
