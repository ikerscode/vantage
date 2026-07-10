import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { Monitor } from "./types";
import { useAuthStore } from "../store/authStore";

interface CreateMonitorInput {
  aoi_id: string;
  schedule: string;
  threshold?: number;
  active?: boolean;
  baseline_date?: string;
}

// BRIEF v2, found for real: see aois.ts's useAois for why this waits on
// token readiness instead of firing unauthenticated and relying on retry.
export function useMonitors() {
  const token = useAuthStore((s) => s.token);
  return useQuery({
    queryKey: ["monitors"],
    queryFn: () => apiFetch<Monitor[]>("/api/monitors"),
    enabled: !!token,
  });
}

export function useCreateMonitor() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateMonitorInput) =>
      apiFetch<Monitor>("/api/monitors", { method: "POST", body: JSON.stringify(input) }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["monitors"] });
    },
  });
}

export function useDeactivateMonitor() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (monitorId: string) =>
      apiFetch<void>(`/api/monitors/${monitorId}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["monitors"] });
    },
  });
}
