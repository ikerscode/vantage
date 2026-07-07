import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { EventRow } from "./types";

export function useEvents() {
  return useQuery({
    queryKey: ["events"],
    queryFn: () => apiFetch<EventRow[]>("/api/events"),
  });
}

// Live SSE delivery is a single shared connection — see
// store/eventStreamStore.ts (ensureEventStreamConnected + useEventStreamStore)
// — rather than a hook every consumer calls independently, which would open
// one long-lived fetch() stream per consumer.
