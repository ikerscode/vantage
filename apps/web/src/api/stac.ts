import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { GeoJSONPolygon, StacItemSummary } from "./types";
import { useAuthStore } from "../store/authStore";

interface StacSearchInput {
  aoi_id?: string;
  geometry?: GeoJSONPolygon;
  date_from: string;
  date_to: string;
  collections?: string[];
  max_cloud_cover?: number;
}

// Scene search is a QUERY keyed by (aoi_id, date range), not a mutation
// (BRIEF v2, found for real: "no imagery until I reload the page every time I
// make an AOI"). As a mutation, `data` was a single component-local result
// with no association to which AOI it belonged to. Selecting a new AOI changed
// selectedAoiId immediately while the previous AOI's scenes were still sitting
// in `data`, so the scrubber's auto-pick effect would latch the NEW AOI onto
// an OLD, non-covering scene and then refuse to correct itself once the real
// results arrived — the map had flown to the new AOI but showed a scene from
// somewhere else, i.e. "no imagery". A keyed query returns `undefined` while a
// new key is in flight (no stale carry-over), and dedupes/caches per AOI+range,
// so each AOI always resolves to its own scenes. Token-gated for the same
// reason useAois is (see api/aois.ts): never fire unauthenticated and rely on
// a 401-then-retry that also trips the global error toast.
export function useStacScenes(input: StacSearchInput | null) {
  const token = useAuthStore((s) => s.token);
  return useQuery({
    queryKey: ["stac-search", input?.aoi_id, input?.geometry, input?.date_from, input?.date_to],
    queryFn: () =>
      apiFetch<StacItemSummary[]>("/api/stac/search", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    enabled: !!token && !!input,
    // Scenes for a given AOI+range don't change moment-to-moment; keep them
    // fresh across quick AOI switches so flipping back is instant.
    staleTime: 5 * 60 * 1000,
  });
}
