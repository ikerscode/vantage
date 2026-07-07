import { create } from "zustand";

export type Mode = "explore" | "analyze" | "monitor";

export interface ViewState {
  longitude: number;
  latitude: number;
  zoom: number;
  pitch: number;
  bearing: number;
}

export interface LatLon {
  lat: number;
  lon: number;
}

interface MapState {
  mode: Mode;
  setMode: (mode: Mode) => void;
  viewState: ViewState;
  setViewState: (viewState: ViewState) => void;
  // Live cursor position off the map instance's own pointer-move handler —
  // feeds both the map's cursor-marker overlay and StatusStrip's CUR field.
  cursorLatLon: LatLon | null;
  setCursorLatLon: (pos: LatLon | null) => void;
  // Set imperatively by CommandBar to ask MapCanvas to fly somewhere; cleared
  // once consumed so repeated jumps to the same place still fire.
  flyToRequest: { longitude: number; latitude: number; zoom?: number } | null;
  requestFlyTo: (target: { longitude: number; latitude: number; zoom?: number }) => void;
  clearFlyToRequest: () => void;
}

export const useMapStore = create<MapState>((set) => ({
  mode: "explore",
  setMode: (mode) => set({ mode }),
  viewState: { longitude: 0, latitude: 20, zoom: 2, pitch: 0, bearing: 0 },
  setViewState: (viewState) => set({ viewState }),
  cursorLatLon: null,
  setCursorLatLon: (cursorLatLon) => set({ cursorLatLon }),
  flyToRequest: null,
  requestFlyTo: (flyToRequest) => set({ flyToRequest }),
  clearFlyToRequest: () => set({ flyToRequest: null }),
}));
