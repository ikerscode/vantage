import { create } from "zustand";

interface AuthState {
  token: string | null;
  setToken: (token: string) => void;
  // SEC-01: the tiler's shared secret, fetched once (see api/auth.ts)
  // after the JWT bootstrap — attached as X-Tiler-Token on every tile
  // request via MapLibre's transformRequest (see components/MapCanvas.tsx).
  tilerToken: string | null;
  setTilerToken: (tilerToken: string) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  setToken: (token) => set({ token }),
  tilerToken: null,
  setTilerToken: (tilerToken) => set({ tilerToken }),
}));
