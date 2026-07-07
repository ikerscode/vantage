import { useMutation } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { GeoJSONPolygon, StacItemSummary } from "./types";

interface StacSearchInput {
  aoi_id?: string;
  geometry?: GeoJSONPolygon;
  date_from: string;
  date_to: string;
  collections?: string[];
  max_cloud_cover?: number;
}

export function useStacSearch() {
  return useMutation({
    mutationFn: (input: StacSearchInput) =>
      apiFetch<StacItemSummary[]>("/api/stac/search", {
        method: "POST",
        body: JSON.stringify(input),
      }),
  });
}
