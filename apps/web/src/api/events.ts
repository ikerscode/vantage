import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { EventRow } from "./types";
import { useAuthStore } from "../store/authStore";

// BRIEF v2, found for real: see aois.ts's useAois for why this waits on
// token readiness instead of firing unauthenticated and relying on retry.
export function useEvents() {
  const token = useAuthStore((s) => s.token);
  return useQuery({
    queryKey: ["events"],
    queryFn: () => apiFetch<EventRow[]>("/api/events"),
    enabled: !!token,
  });
}

// Live SSE delivery is a single shared connection — see
// store/eventStreamStore.ts (ensureEventStreamConnected + useEventStreamStore)
// — rather than a hook every consumer calls independently, which would open
// one long-lived fetch() stream per consumer.
