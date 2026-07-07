import { useState } from "react";

import { useCreateMonitor, useDeactivateMonitor } from "../api/monitors";
import { useMonitorAlertStatus } from "../lib/monitorAlerts";
import { useAnalysisStore } from "../store/analysisStore";
import { useAoiStore } from "../store/aoiStore";

const SCHEDULE_PRESETS: { label: string; cron: string }[] = [
  { label: "HOURLY", cron: "0 * * * *" },
  { label: "DAILY", cron: "0 6 * * *" },
  { label: "WEEKLY", cron: "0 6 * * 1" },
];

type Status = "ALERT" | "WATCHING" | "PAUSED";

function statusOf(active: boolean, isAlert: boolean): Status {
  if (!active) return "PAUSED";
  return isAlert ? "ALERT" : "WATCHING";
}

const STATUS_DOT_COLOR: Record<Status, string> = {
  ALERT: "var(--alert)",
  WATCHING: "var(--nominal)",
  PAUSED: "var(--text-tertiary)",
};

export function MonitorPanel() {
  const selectedAoiId = useAoiStore((s) => s.selectedAoiId);
  const setInspectorTarget = useAnalysisStore((s) => s.setInspectorTarget);

  const { monitors, alertMonitorIds } = useMonitorAlertStatus();
  const createMonitor = useCreateMonitor();
  const deactivateMonitor = useDeactivateMonitor();

  const [schedule, setSchedule] = useState(SCHEDULE_PRESETS[1].cron);
  const [threshold, setThreshold] = useState("");
  const [baselineDate, setBaselineDate] = useState("");

  const alertCount = monitors.filter((m) => alertMonitorIds.has(m.id)).length;

  const handleCreate = () => {
    if (!selectedAoiId) return;
    createMonitor.mutate({
      aoi_id: selectedAoiId,
      schedule,
      threshold: threshold ? Number(threshold) : undefined,
      baseline_date: baselineDate || undefined,
    });
  };

  return (
    <div className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Monitors</h2>
        <span className="panel-header-meta">
          {monitors.length} · {alertCount} ALERT
        </span>
      </div>

      <div className="monitor-form">
        {!selectedAoiId && <span className="hint" style={{ padding: 0 }}>select an AOI to add a monitor</span>}
        {selectedAoiId && (
          <>
            <div className="monitor-form-presets">
              {SCHEDULE_PRESETS.map((preset) => (
                <button
                  key={preset.cron}
                  className={schedule === preset.cron ? "tag tag-active" : "tag"}
                  onClick={() => setSchedule(preset.cron)}
                >
                  {preset.label}
                </button>
              ))}
            </div>
            <input
              className="text-input"
              value={schedule}
              onChange={(e) => setSchedule(e.target.value)}
              placeholder="cron schedule"
            />
            <input
              className="text-input"
              type="number"
              step={0.05}
              min={0}
              max={1}
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              placeholder="NDVI threshold (default 0.2)"
            />
            <input
              className="text-input"
              type="date"
              value={baselineDate}
              onChange={(e) => setBaselineDate(e.target.value)}
            />
            <button className="tag" onClick={handleCreate} disabled={createMonitor.isPending}>
              CREATE MONITOR
            </button>
          </>
        )}
      </div>

      <ul className="row-list">
        {monitors.map((monitor) => {
          const status = statusOf(monitor.active, alertMonitorIds.has(monitor.id));
          return (
            <li
              key={monitor.id}
              className={status === "ALERT" ? "row alert-row" : "row"}
              style={{ flexDirection: "column", alignItems: "stretch", gap: 5 }}
              onClick={() => setInspectorTarget({ kind: "monitor", id: monitor.id })}
            >
              <div className="row-bar" />
              <div className="monitor-row-line1">
                <div className="monitor-row-name-group">
                  <span className="monitor-status-dot" style={{ background: STATUS_DOT_COLOR[status] }} />
                  <span className="monitor-name">{monitor.schedule}</span>
                </div>
                <button
                  className={monitor.active ? "switch on" : "switch"}
                  title={monitor.active ? "Deactivate" : "Reactivating isn't supported by the API yet"}
                  disabled={!monitor.active}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (monitor.active) deactivateMonitor.mutate(monitor.id);
                  }}
                >
                  <span className="switch-knob" />
                </button>
              </div>
              <div className="monitor-row-line2">
                <span>{status}</span>
                <span>{monitor.last_run_at ? `last ${monitor.last_run_at.slice(11, 16).replace(":", "")}Z` : "last —"}</span>
              </div>
            </li>
          );
        })}
        {monitors.length === 0 && <li className="hint">no monitors yet</li>}
      </ul>
    </div>
  );
}
