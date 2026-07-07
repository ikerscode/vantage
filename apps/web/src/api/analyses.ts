import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { AnalysisResult } from "./types";

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

export function useAnalyses(aoiId: string | undefined) {
  return useQuery({
    queryKey: ["analyses", aoiId],
    queryFn: () => apiFetch<AnalysisResult[]>(`/api/analyses${aoiId ? `?aoi_id=${aoiId}` : ""}`),
  });
}

const IN_PROGRESS_POLL_MS = 2000;

export function useAnalysis(analysisId: string | undefined) {
  return useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: () => apiFetch<AnalysisResult>(`/api/analyses/${analysisId}`),
    enabled: !!analysisId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "running" ? IN_PROGRESS_POLL_MS : false;
    },
  });
}
