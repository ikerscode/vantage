import { create } from "zustand";

export type ToastKind = "alert" | "error";

export interface AppToast {
  id: string;
  kind: ToastKind;
  title: string;
  summary: string;
  time: string;
}

interface ToastState {
  toasts: AppToast[];
  pushToast: (toast: AppToast) => void;
  dismissToast: (id: string) => void;
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  pushToast: (toast) =>
    set((state) => ({
      // De-dupe by id (the event stream can replay, and a flaky connection
      // can retry the same failing request) — don't stack the same toast twice.
      toasts: state.toasts.some((t) => t.id === toast.id) ? state.toasts : [toast, ...state.toasts].slice(0, 3),
    })),
  dismissToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}));

/** BRIEF v2: every mutation/query failure in the app routes through this,
 * via main.tsx's QueryClient (MutationCache/QueryCache onError) — see that
 * file's comment. Nothing should ever fail completely silently again.
 *
 * `code` (e.g. VG-401, VG-TIMEOUT) is surfaced in the toast title so a user
 * can report precisely what failed instead of a generic "something went
 * wrong" — see api/client.ts's ApiError.code. */
export function pushErrorToast(message: string, code?: string): void {
  useToastStore.getState().pushToast({
    id: `error-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    kind: "error",
    title: code ? `Something went wrong · ${code}` : "Something went wrong",
    summary: message,
    time: new Date().toISOString().slice(11, 16).replace(":", "") + "Z",
  });
}
