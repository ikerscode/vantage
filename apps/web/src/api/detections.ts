import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { Detection } from "./types";
import { useAuthStore } from "../store/authStore";

// BRIEF v2, found for real: see aois.ts's useAois for why this waits on
// token readiness too, not just analysisId, instead of firing
// unauthenticated and relying on retry.
export function useDetections(analysisId: string | undefined) {
  const token = useAuthStore((s) => s.token);
  return useQuery({
    queryKey: ["detections", analysisId],
    queryFn: () => apiFetch<Detection[]>(`/api/detections?analysis_id=${analysisId}`),
    enabled: !!analysisId && !!token,
  });
}
