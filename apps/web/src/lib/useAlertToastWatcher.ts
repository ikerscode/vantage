import { useEffect, useRef } from "react";

import { useAois } from "../api/aois";
import { useEventStreamStore } from "../store/eventStreamStore";
import { useToastStore } from "../store/toastStore";

// Only toast events that just arrived (age < this window) — the SSE
// connection replays unseen historical rows on connect too (see
// apps/api's /api/events/stream), and those shouldn't spam toasts on load.
const FRESH_WINDOW_MS = 30_000;

export function useAlertToastWatcher(): void {
  const events = useEventStreamStore((s) => s.events);
  const pushToast = useToastStore((s) => s.pushToast);
  const { data: aois } = useAois();
  const seenRef = useRef(new Set<string>());

  useEffect(() => {
    for (const event of events) {
      if (seenRef.current.has(event.id)) continue;
      seenRef.current.add(event.id);
      const age = Date.now() - new Date(event.created_at).getTime();
      if (age > FRESH_WINDOW_MS) continue;

      const aoiName = aois?.find((a) => a.id === event.aoi_id)?.name ?? event.aoi_id.slice(0, 8);
      pushToast({
        id: event.id,
        kind: "alert",
        title: `Monitor tripped — ${aoiName}`,
        summary: event.summary,
        time: event.created_at.slice(11, 16).replace(":", "") + "Z",
      });
    }
  }, [events, aois, pushToast]);
}
