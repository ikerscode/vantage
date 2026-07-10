import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { AOI, GeoJSONPolygon } from "./types";
import { useAuthStore } from "../store/authStore";

// BRIEF v2, found for real on a live device: this (and every other
// top-level list query -- events, monitors, analyses) fired immediately on
// mount, before useDevAuthBootstrap's async token fetch had resolved, so
// every one of them 401'd on first load -- relying entirely on TanStack
// Query's blind retry-after-error to self-heal once the token showed up a
// moment later (and firing the new global error toast for something that
// was never really an error). Gating on token readiness means these
// requests are never even attempted unauthenticated in the first place.
export function useAois() {
  const token = useAuthStore((s) => s.token);
  return useQuery({
    queryKey: ["aois"],
    queryFn: () => apiFetch<AOI[]>("/api/aois"),
    enabled: !!token,
  });
}

interface CreateAoiInput {
  name: string;
  description?: string;
  geometry: GeoJSONPolygon;
}

export function useCreateAoi() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateAoiInput) =>
      apiFetch<AOI>("/api/aois", { method: "POST", body: JSON.stringify(input) }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["aois"] });
    },
  });
}

export function useArchiveAoi() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (aoiId: string) => apiFetch<void>(`/api/aois/${aoiId}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["aois"] });
    },
  });
}
