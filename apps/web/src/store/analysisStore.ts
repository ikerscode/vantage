import { create } from "zustand";

import type { StacItemSummary } from "../api/types";

// Opacity is tracked for every raster, but only the base layers are
// mutually exclusive (exactly one on at a time). Change is an OVERLAY that
// stacks on top of whichever base is showing — see BaseRasterLayerId.
// sar_amplitude/sar_false_color are SAR AOIs' equivalent of true_color/ndvi
// (see lib/sensor.ts) — an AOI only ever offers one pair or the other, never
// all four at once (LayersControl filters by the selected AOI's collection).
export type RasterLayerId = "true_color" | "ndvi" | "sar_amplitude" | "sar_false_color" | "change";
// The base imagery layer. Exactly one is always active so real imagery stays
// visible underneath the Change/Detections overlays (a live request: selecting
// Change must NOT blank the map — the imagery has to stay on).
export type BaseRasterLayerId = "true_color" | "ndvi" | "sar_amplitude" | "sar_false_color";
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
  // Base imagery (True Color / NDVI) is mutually exclusive — exactly one is
  // always on, so imagery never disappears out from under the overlays.
  // Change and Detections are independent overlays that STACK on top of it.
  activeRasterLayer: BaseRasterLayerId;
  setActiveRasterLayer: (layer: BaseRasterLayerId) => void;
  rasterOpacity: Record<RasterLayerId, number>;
  setRasterOpacity: (layer: RasterLayerId, opacity: number) => void;
  // Change overlay — the colorized NDVI-diff raster from the active analysis.
  changeVisible: boolean;
  toggleChangeVisible: () => void;
  setChangeVisible: (visible: boolean) => void;
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
  // Selecting a base layer always switches to it (never toggles off) — one
  // base is always active so the map is never left blank while an overlay is on.
  activeRasterLayer: "true_color",
  setActiveRasterLayer: (layer) => set({ activeRasterLayer: layer }),
  rasterOpacity: { true_color: 1, ndvi: 0.8, sar_amplitude: 1, sar_false_color: 0.85, change: 0.75 },
  setRasterOpacity: (layer, opacity) =>
    set((state) => ({ rasterOpacity: { ...state.rasterOpacity, [layer]: opacity } })),
  changeVisible: false,
  toggleChangeVisible: () => set((state) => ({ changeVisible: !state.changeVisible })),
  setChangeVisible: (changeVisible) => set({ changeVisible }),
  detectionsVisible: false,
  toggleDetectionsVisible: () => set((state) => ({ detectionsVisible: !state.detectionsVisible })),
  inspectorTarget: null,
  setInspectorTarget: (inspectorTarget) => set({ inspectorTarget }),
}));
