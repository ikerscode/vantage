import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { AOI, GeoJSONPolygon } from "./types";

export function useAois() {
  return useQuery({
    queryKey: ["aois"],
    queryFn: () => apiFetch<AOI[]>("/api/aois"),
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
