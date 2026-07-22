import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import { useAuthStore } from "../store/authStore";

export interface InferenceStatus {
  reachable: boolean;
  model_backend: string | null;
  device: string | null;
}

// Backend-reported detector identity for LayersControl's honest-seam note
// (CLAUDE.md §3). Found live: the note used to hardcode "COCO placeholder,
// expects nothing" and kept saying so after the deployment had switched to
// the fine-tuned vessel backend — the UI has no business asserting server
// config it can't see, so now it asks. silent: an unreachable inference
// service is an expected state the note itself communicates in place; a
// global error toast on top would be noise. staleTime keeps this to one
// probe a minute, not one per panel re-render.
export function useInferenceStatus() {
  const token = useAuthStore((s) => s.token);
  return useQuery({
    queryKey: ["inference-status"],
    queryFn: () => apiFetch<InferenceStatus>("/api/inference/status"),
    enabled: !!token,
    staleTime: 60_000,
    meta: { silent: true },
  });
}
