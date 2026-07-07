import { create } from "zustand";

import { API_BASE_URL } from "../api/client";
import type { EventRow } from "../api/types";

export type SseStatus = "connecting" | "open" | "down";

const MAX_BUFFERED_EVENTS = 100;

interface EventStreamState {
  events: EventRow[];
  status: SseStatus;
  connectedToken: string | null;
}

// A single shared SSE connection for the whole app — StatusStrip, ResultsFeed,
// and the alert-toast watcher all read from this store instead of each
// opening their own long-lived fetch() stream to /api/events/stream.
export const useEventStreamStore = create<EventStreamState>(() => ({
  events: [],
  status: "connecting",
  connectedToken: null,
}));

let activeController: AbortController | null = null;

export function ensureEventStreamConnected(token: string | null): void {
  const current = useEventStreamStore.getState();
  if (!token) {
    activeController?.abort();
    activeController = null;
    useEventStreamStore.setState({ status: "down", connectedToken: null });
    return;
  }
  if (current.connectedToken === token && activeController) return;

  activeController?.abort();
  const controller = new AbortController();
  activeController = controller;
  useEventStreamStore.setState({ status: "connecting", connectedToken: token });

  (async () => {
    const response = await fetch(`${API_BASE_URL}/api/events/stream`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    });
    if (!response.ok || !response.body) {
      useEventStreamStore.setState({ status: "down" });
      return;
    }
    useEventStreamStore.setState({ status: "open" });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        const dataLine = part.split("\n").find((line) => line.startsWith("data: "));
        if (!dataLine) continue;
        try {
          const event = JSON.parse(dataLine.slice("data: ".length)) as EventRow;
          useEventStreamStore.setState((s) => ({ events: [event, ...s.events].slice(0, MAX_BUFFERED_EVENTS) }));
        } catch {
          // ignore malformed chunk
        }
      }
    }
  })().catch((err: unknown) => {
    if (!controller.signal.aborted) {
      console.error("event stream error", err);
      useEventStreamStore.setState({ status: "down" });
    }
  });
}
