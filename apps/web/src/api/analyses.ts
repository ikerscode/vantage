import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { AnalysisResult } from "./types";
import { useAuthStore } from "../store/authStore";

interface CreateAnalysisInput {
  aoi_id: string;
  date_a: string;
  date_b: string;
  threshold?: number;
}

export function useCreateAnalysis() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateAnalysisInput) =>
      apiFetch<AnalysisResult>("/api/analyses", { method: "POST", body: JSON.stringify(input) }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["analyses"] });
    },
  });
}

// BRIEF v2, found for real: see aois.ts's useAois for why this waits on
// token readiness instead of firing unauthenticated and relying on retry.
export function useAnalyses(aoiId: string | undefined) {
  const token = useAuthStore((s) => s.token);
  return useQuery({
    queryKey: ["analyses", aoiId],
    queryFn: () => apiFetch<AnalysisResult[]>(`/api/analyses${aoiId ? `?aoi_id=${aoiId}` : ""}`),
    enabled: !!token,
  });
}

const IN_PROGRESS_POLL_MS = 2000;

export function useAnalysis(analysisId: string | undefined) {
  const token = useAuthStore((s) => s.token);
  return useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: () => apiFetch<AnalysisResult>(`/api/analyses/${analysisId}`),
    enabled: !!analysisId && !!token,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "running" ? IN_PROGRESS_POLL_MS : false;
    },
  });
}
