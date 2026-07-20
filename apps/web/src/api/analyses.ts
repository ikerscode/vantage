import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { apiFetch } from "./client";
import type { AnalysisResult, AnalysisStatus } from "./types";
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

// Past this, a still-"pending"/"running" analysis is treated as STALLED and we
// stop polling — the same philosophy as apiFetch's REQUEST_TIMEOUT_MS (see
// api/client.ts): an unbounded in-progress state must resolve to a visible,
// terminal state rather than an indeterminate bar that spins forever. A wedged
// Celery worker (not running, or killed mid-run) leaves the row stuck at
// pending/running with no terminal transition ever coming; without this the
// Results job-card bar (and this poll) would run indefinitely. Generous on
// purpose: a cold first run reads two scenes' bands from remote COGs, writes +
// uploads a COG, then runs inference over up to 9 chips — minutes, not seconds
// — so this sits well clear of any legitimately slow run.
export const ANALYSIS_STALL_MS = 5 * 60 * 1000;

/** True once an in-progress analysis has been pending/running past
 * ANALYSIS_STALL_MS — i.e. it should be shown as stalled, not still working. */
export function analysisIsStalled(
  analysis: { status: AnalysisStatus; created_at: string } | undefined | null,
): boolean {
  if (!analysis) return false;
  if (analysis.status !== "pending" && analysis.status !== "running") return false;
  const startedAt = new Date(analysis.created_at).getTime();
  return Number.isFinite(startedAt) && Date.now() - startedAt > ANALYSIS_STALL_MS;
}

// Found live (running a real analysis end-to-end against Souda Bay imagery):
// app.tasks.change_detection commits AnalysisResult.status = "done" INSIDE
// execute_change_detection, then runs the best-effort object-detection
// sub-step and commits detection_status/detection_count/detection_error
// AFTERWARD, in the same task — a real gap (inference is a real network call
// + model forward pass, genuinely seconds to tens of seconds). Stopping the
// poll the instant status goes terminal (the original rule below) means that
// second commit lands after the last poll fired: the Inspector's DETECTION
// row and the pulsing-red detection boxes on the map would never appear for
// an analysis that had genuine detections, staying silently frozen at
// "not tracked yet" forever. This grace window keeps polling a short while
// past "done" specifically until detection_status shows up too — bounded so
// a SAR AOI (detection SKIPPED almost immediately) or a stuck detection step
// can't keep the poll running indefinitely.
const DETECTION_GRACE_MS = 90 * 1000;

export function useAnalysis(analysisId: string | undefined) {
  const token = useAuthStore((s) => s.token);
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["analysis", analysisId],
    queryFn: () => apiFetch<AnalysisResult>(`/api/analyses/${analysisId}`),
    enabled: !!analysisId && !!token,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      const inProgress = data.status === "pending" || data.status === "running";
      if (inProgress) return analysisIsStalled(data) ? false : IN_PROGRESS_POLL_MS;
      if (data.status === "done" && data.detection_status == null && data.completed_at) {
        const completedAt = new Date(data.completed_at).getTime();
        if (Number.isFinite(completedAt) && Date.now() - completedAt < DETECTION_GRACE_MS) {
          return IN_PROGRESS_POLL_MS;
        }
      }
      return false;
    },
  });

  // The Results Feed's analyses LIST (useAnalyses below) is a separate cache
  // entry that nothing else refreshes once creation-time's one-shot
  // invalidation (useCreateAnalysis's onSuccess, fired back when this
  // analysis was still "pending") has already happened — found live: a
  // just-completed run stayed permanently absent from Results until an
  // unrelated refetch happened to occur (e.g. a manual reload). Re-invalidate
  // once this specific analysis reaches a terminal status, so the row that
  // just finished actually shows up.
  const invalidatedListForId = useRef<string | null>(null);
  useEffect(() => {
    const data = query.data;
    if (!data || !analysisId) return;
    const settled = data.status === "done" || data.status === "failed";
    if (!settled || invalidatedListForId.current === analysisId) return;
    invalidatedListForId.current = analysisId;
    void queryClient.invalidateQueries({ queryKey: ["analyses"] });
  }, [query.data, analysisId, queryClient]);

  // Detections get their OWN separate invalidation, on their OWN trigger
  // (detection_status actually landing) rather than piggybacking on the
  // "analysis settled" one above. Found live: bundling them meant the
  // detections list got invalidated at the same moment status flipped to
  // "done" — which, per DETECTION_GRACE_MS's comment above, is typically
  // BEFORE the detection sub-step has actually written its rows. That
  // refetch cached an empty list, and with nothing invalidating it again
  // once the real detections landed a few seconds later, the Results Feed
  // (and map's detection boxes) stayed empty forever despite the Inspector
  // correctly showing a real, nonzero DETECTION count.
  const invalidatedDetectionsForId = useRef<string | null>(null);
  useEffect(() => {
    const data = query.data;
    if (!data || !analysisId || data.detection_status == null) return;
    if (invalidatedDetectionsForId.current === analysisId) return;
    invalidatedDetectionsForId.current = analysisId;
    void queryClient.invalidateQueries({ queryKey: ["detections", analysisId] });
  }, [query.data, analysisId, queryClient]);

  return query;
}
