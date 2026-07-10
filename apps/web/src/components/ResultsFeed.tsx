import { useMemo } from "react";

import { useAnalyses, useAnalysis } from "../api/analyses";
import { useDetections } from "../api/detections";
import { useEvents } from "../api/events";
import type { EventRow } from "../api/types";
import { useAnalysisStore } from "../store/analysisStore";
import { useAoiStore } from "../store/aoiStore";
import { useEventStreamStore } from "../store/eventStreamStore";
import { useMapStore } from "../store/mapStore";

const ALERT_WINDOW_MS = 10 * 60 * 1000;

interface FeedRow {
  key: string;
  kind: "CHG" | "DET";
  label: string;
  meta: string;
  conf: string;
  time: string;
  onClick: () => void;
}

export function ResultsFeed() {
  const mode = useMapStore((s) => s.mode);
  const selectedAoiId = useAoiStore((s) => s.selectedAoiId);
  const activeAnalysisId = useAnalysisStore((s) => s.activeAnalysisId);
  const setInspectorTarget = useAnalysisStore((s) => s.setInspectorTarget);
  const setActiveAnalysisId = useAnalysisStore((s) => s.setActiveAnalysisId);

  const { data: activeAnalysis } = useAnalysis(activeAnalysisId ?? undefined);
  const { data: analyses } = useAnalyses(selectedAoiId ?? undefined);
  const { data: detections } = useDetections(activeAnalysisId ?? undefined);

  const { data: initialEvents } = useEvents();
  const liveEvents = useEventStreamStore((s) => s.events);
  const sseStatus = useEventStreamStore((s) => s.status);

  const events = useMemo(() => {
    const byId = new Map<string, EventRow>();
    for (const event of initialEvents ?? []) byId.set(event.id, event);
    for (const event of liveEvents) byId.set(event.id, event);
    return Array.from(byId.values()).sort((a, b) => b.created_at.localeCompare(a.created_at));
  }, [initialEvents, liveEvents]);

  const jobPending = activeAnalysis && (activeAnalysis.status === "pending" || activeAnalysis.status === "running");

  if (mode === "monitor") {
    const now = Date.now();
    return (
      <div className="panel" style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
        <div className="panel-header">
          <h2 className="panel-title">Live Events</h2>
          <div className="stream-indicator">
            <span className="stream-dot" />
            <span className="panel-header-meta">{sseStatus === "open" ? "SUBSCRIBED" : "DOWN"}</span>
          </div>
        </div>
        <ul className="row-list" style={{ flex: 1 }}>
          {events.map((event) => {
            const isRecent = now - new Date(event.created_at).getTime() <= ALERT_WINDOW_MS;
            return (
              <li
                key={event.id}
                className={isRecent ? "row alert-row" : "row"}
                onClick={() => setInspectorTarget({ kind: "event", id: event.id })}
              >
                <div className="row-bar" />
                <span className="result-kind-chip">{isRecent ? "ALERT" : "CHG"}</span>
                <div className="result-body">
                  <div className="result-label">{event.summary}</div>
                </div>
                <div className="result-right">
                  <div className="result-conf">{(event.metric_value * 100).toFixed(1)}%</div>
                  <div className="result-time">{event.created_at.slice(11, 16).replace(":", "")}Z</div>
                </div>
              </li>
            );
          })}
          {events.length === 0 && <li className="hint">no events yet</li>}
        </ul>
      </div>
    );
  }

  const rows: FeedRow[] = [];
  for (const analysis of analyses ?? []) {
    if (analysis.status !== "done") continue;
    const pct = analysis.stats?.pct_changed;
    rows.push({
      key: `analysis-${analysis.id}`,
      kind: "CHG",
      label: `Change ${analysis.date_a} → ${analysis.date_b}`,
      meta: `threshold ${analysis.threshold}`,
      conf: pct != null ? `${(pct * 100).toFixed(1)}%` : "—",
      time: (analysis.completed_at ?? analysis.created_at).slice(11, 16).replace(":", "") + "Z",
      // BRIEF v2, found for real: this only ever set inspectorTarget, so
      // MapCanvas's Change layer (keyed off activeAnalysisId, not
      // inspectorTarget) never had anything to render for a PAST analysis --
      // toggling "Change" after clicking an old result here just went dark,
      // indistinguishable from the layer being broken. Only a just-run
      // analysis (TemporalScrubber's handleRunAnalysis) ever set this before.
      onClick: () => {
        setInspectorTarget({ kind: "analysis", id: analysis.id });
        setActiveAnalysisId(analysis.id);
      },
    });
  }
  for (const detection of detections ?? []) {
    rows.push({
      key: `detection-${detection.id}`,
      kind: "DET",
      label: detection.label,
      meta: `chip · ${detection.chip_s3_key.split("/").pop()}`,
      conf: detection.score.toFixed(2),
      time: detection.created_at.slice(11, 16).replace(":", "") + "Z",
      onClick: () => setInspectorTarget({ kind: "detection", id: detection.id }),
    });
  }
  rows.sort((a, b) => b.time.localeCompare(a.time));

  return (
    <div className="panel" style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div className="panel-header">
        <h2 className="panel-title">Results</h2>
        <div className="stream-indicator">
          <span className="stream-dot" />
          <span className="panel-header-meta">STREAMING</span>
        </div>
      </div>
      {jobPending && (
        <div className="job-card">
          <div className="job-card-header">
            <span className="job-card-name">CHANGE DETECTION · {activeAnalysis.status.toUpperCase()}</span>
          </div>
          <div className="job-card-track">
            <div className="job-card-fill indeterminate" />
          </div>
        </div>
      )}
      <ul className="row-list" style={{ flex: 1 }}>
        {rows.map((row) => (
          <li key={row.key} className="row" onClick={row.onClick}>
            <div className="row-bar" />
            <span className="result-kind-chip">{row.kind}</span>
            <div className="result-body">
              <div className="result-label">{row.label}</div>
              <div className="result-meta">{row.meta}</div>
            </div>
            <div className="result-right">
              <div className="result-conf">{row.conf}</div>
              <div className="result-time">{row.time}</div>
            </div>
          </li>
        ))}
        {rows.length === 0 && <li className="hint">no results yet</li>}
      </ul>
    </div>
  );
}
