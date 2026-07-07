import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { Detection } from "./types";

export function useDetections(analysisId: string | undefined) {
  return useQuery({
    queryKey: ["detections", analysisId],
    queryFn: () => apiFetch<Detection[]>(`/api/detections?analysis_id=${analysisId}`),
    enabled: !!analysisId,
  });
}
