import { create } from "zustand";

import type { GeoJSONPolygon } from "../api/types";

interface AoiState {
  selectedAoiId: string | null;
  setSelectedAoiId: (id: string | null) => void;
  draftGeometry: GeoJSONPolygon | null;
  setDraftGeometry: (geometry: GeoJSONPolygon | null) => void;
  isDrawing: boolean;
  setIsDrawing: (isDrawing: boolean) => void;
  // Reshaping an EXISTING AOI's geometry (drag vertices on the map), as
  // opposed to draftGeometry/isDrawing above (drawing a brand-new one from
  // scratch). Kept as separate state rather than reusing draftGeometry:
  // the two interactions have different Cancel semantics (cancel-drawing
  // discards a not-yet-saved shape; cancel-editing reverts to the AOI's
  // last-saved geometry) and can't be conflated without one silently
  // clobbering the other if a user starts one mid-way through the other.
  editingAoiId: string | null;
  setEditingAoiId: (id: string | null) => void;
  editingGeometry: GeoJSONPolygon | null;
  setEditingGeometry: (geometry: GeoJSONPolygon | null) => void;
}

export const useAoiStore = create<AoiState>((set) => ({
  selectedAoiId: null,
  setSelectedAoiId: (id) => set({ selectedAoiId: id }),
  draftGeometry: null,
  setDraftGeometry: (geometry) => set({ draftGeometry: geometry }),
  isDrawing: false,
  setIsDrawing: (isDrawing) => set({ isDrawing }),
  editingAoiId: null,
  setEditingAoiId: (id) => set({ editingAoiId: id }),
  editingGeometry: null,
  setEditingGeometry: (geometry) => set({ editingGeometry: geometry }),
}));
