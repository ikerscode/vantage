import { create } from "zustand";

export interface AlertToast {
  id: string;
  monitorName: string;
  summary: string;
  time: string;
}

interface ToastState {
  toasts: AlertToast[];
  pushToast: (toast: AlertToast) => void;
  dismissToast: (id: string) => void;
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  pushToast: (toast) =>
    set((state) => ({
      // De-dupe by id (the event stream can replay) — don't stack the same alert twice.
      toasts: state.toasts.some((t) => t.id === toast.id) ? state.toasts : [toast, ...state.toasts].slice(0, 3),
    })),
  dismissToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}));
