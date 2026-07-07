import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { Monitor } from "./types";

interface CreateMonitorInput {
  aoi_id: string;
  schedule: string;
  threshold?: number;
  active?: boolean;
  baseline_date?: string;
}

export function useMonitors() {
  return useQuery({
    queryKey: ["monitors"],
    queryFn: () => apiFetch<Monitor[]>("/api/monitors"),
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
