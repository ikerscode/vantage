import { useEvents } from "../api/events";
import { useMonitors } from "../api/monitors";
import type { EventRow, Monitor } from "../api/types";

// The real Monitor model has no "status" enum (ALERT/WATCHING/PAUSED) — only
// active: boolean. We derive ALERT from real data instead of faking a field:
// a monitor is "in alert" if one of its Events landed within this window.
const ALERT_WINDOW_MS = 10 * 60 * 1000;

export interface MonitorAlertStatus {
  monitors: Monitor[];
  latestEventByMonitor: Map<string, EventRow>;
  alertMonitorIds: Set<string>;
  alertMonitors: Monitor[];
  isAnyAlert: boolean;
}

export function useMonitorAlertStatus(): MonitorAlertStatus {
  const { data: monitors } = useMonitors();
  const { data: events } = useEvents();

  const latestEventByMonitor = new Map<string, EventRow>();
  for (const event of events ?? []) {
    const existing = latestEventByMonitor.get(event.monitor_id);
    if (!existing || event.created_at > existing.created_at) {
      latestEventByMonitor.set(event.monitor_id, event);
    }
  }

  const now = Date.now();
  const alertMonitorIds = new Set<string>();
  for (const [monitorId, event] of latestEventByMonitor) {
    if (now - new Date(event.created_at).getTime() <= ALERT_WINDOW_MS) {
      alertMonitorIds.add(monitorId);
    }
  }

  const alertMonitors = (monitors ?? []).filter((m) => alertMonitorIds.has(m.id));

  return {
    monitors: monitors ?? [],
    latestEventByMonitor,
    alertMonitorIds,
    alertMonitors,
    isAnyAlert: alertMonitors.length > 0,
  };
}
