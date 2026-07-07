import { create } from "zustand";

import type { GeoJSONPolygon } from "../api/types";

interface AoiState {
  selectedAoiId: string | null;
  setSelectedAoiId: (id: string | null) => void;
  draftGeometry: GeoJSONPolygon | null;
  setDraftGeometry: (geometry: GeoJSONPolygon | null) => void;
  isDrawing: boolean;
  setIsDrawing: (isDrawing: boolean) => void;
}

export const useAoiStore = create<AoiState>((set) => ({
  selectedAoiId: null,
  setSelectedAoiId: (id) => set({ selectedAoiId: id }),
  draftGeometry: null,
  setDraftGeometry: (geometry) => set({ draftGeometry: geometry }),
  isDrawing: false,
  setIsDrawing: (isDrawing) => set({ isDrawing }),
}));
