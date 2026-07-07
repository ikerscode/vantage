import { create } from "zustand";

import type { StacItemSummary } from "../api/types";

export type RasterLayerId = "true_color" | "ndvi" | "change";
export type ScrubberMode = "single" | "before-after";

export type InspectorTarget = {
  kind: "aoi" | "analysis" | "monitor" | "event" | "detection";
  id: string;
} | null;

interface AnalysisState {
  scrubberMode: ScrubberMode;
  setScrubberMode: (mode: ScrubberMode) => void;
  // Single-date mode (Explore): one date drives the True Color/NDVI preview.
  singleDate: string | null;
  setSingleDate: (date: string | null) => void;
  // Before/after mode (Analyze): the two dates a change-detection job compares.
  dateA: string | null;
  dateB: string | null;
  setDateA: (date: string | null) => void;
  setDateB: (date: string | null) => void;
  // The scene picked for the Explore/Analyze true-color/NDVI raster preview.
  selectedScene: StacItemSummary | null;
  setSelectedScene: (scene: StacItemSummary | null) => void;
  activeAnalysisId: string | null;
  setActiveAnalysisId: (id: string | null) => void;
  // Raster layers (True Color / NDVI / Change) are mutually exclusive — only
  // one can be on the map at a time. Detections is an independent vector
  // toggle that stacks with whichever raster (or none) is active.
  activeRasterLayer: RasterLayerId | null;
  setActiveRasterLayer: (layer: RasterLayerId | null) => void;
  rasterOpacity: Record<RasterLayerId, number>;
  setRasterOpacity: (layer: RasterLayerId, opacity: number) => void;
  detectionsVisible: boolean;
  toggleDetectionsVisible: () => void;
  inspectorTarget: InspectorTarget;
  setInspectorTarget: (target: InspectorTarget) => void;
}

export const useAnalysisStore = create<AnalysisState>((set) => ({
  scrubberMode: "single",
  setScrubberMode: (scrubberMode) => set({ scrubberMode }),
  singleDate: null,
  setSingleDate: (singleDate) => set({ singleDate }),
  dateA: null,
  dateB: null,
  setDateA: (dateA) => set({ dateA }),
  setDateB: (dateB) => set({ dateB }),
  selectedScene: null,
  setSelectedScene: (selectedScene) => set({ selectedScene }),
  activeAnalysisId: null,
  setActiveAnalysisId: (activeAnalysisId) => set({ activeAnalysisId }),
  activeRasterLayer: "true_color",
  setActiveRasterLayer: (layer) =>
    set((state) => ({ activeRasterLayer: state.activeRasterLayer === layer ? null : layer })),
  rasterOpacity: { true_color: 1, ndvi: 0.8, change: 0.65 },
  setRasterOpacity: (layer, opacity) =>
    set((state) => ({ rasterOpacity: { ...state.rasterOpacity, [layer]: opacity } })),
  detectionsVisible: false,
  toggleDetectionsVisible: () => set((state) => ({ detectionsVisible: !state.detectionsVisible })),
  inspectorTarget: null,
  setInspectorTarget: (inspectorTarget) => set({ inspectorTarget }),
}));
