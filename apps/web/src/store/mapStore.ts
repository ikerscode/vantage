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
  // once consumed so repeated jumps to the same place still fire. `instant`
  // jumps with no animation (used for the first auto-navigation so the user
  // doesn't watch a multi-second fly across the empty void before imagery).
  flyToRequest: { longitude: number; latitude: number; zoom?: number; instant?: boolean } | null;
  requestFlyTo: (target: { longitude: number; latitude: number; zoom?: number; instant?: boolean }) => void;
  clearFlyToRequest: () => void;
  // Bumped by the compass to ask MapCanvas to rotate the map back to north-up
  // (bearing 0, pitch 0). A nonce rather than a boolean so repeated presses
  // always re-fire even when already near north.
  northUpNonce: number;
  requestNorthUp: () => void;
}

export const useMapStore = create<MapState>((set) => ({
  mode: "explore",
  setMode: (mode) => set({ mode }),
  // Opens at a regional zoom, not world scale — see MapCanvas's MIN_ZOOM
  // (the map also enforces that as a hard floor). A fresh install with no
  // AOIs yet still lands somewhere you could immediately draw a usable one.
  viewState: { longitude: 0, latitude: 20, zoom: 10, pitch: 0, bearing: 0 },
  setViewState: (viewState) => set({ viewState }),
  cursorLatLon: null,
  setCursorLatLon: (cursorLatLon) => set({ cursorLatLon }),
  flyToRequest: null,
  requestFlyTo: (flyToRequest) => set({ flyToRequest }),
  clearFlyToRequest: () => set({ flyToRequest: null }),
  northUpNonce: 0,
  requestNorthUp: () => set((s) => ({ northUpNonce: s.northUpNonce + 1 })),
}));
