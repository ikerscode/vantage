import { useMemo } from "react";

import { useAnalyses, useAnalysis, analysisIsStalled } from "../api/analyses";
import { useAois } from "../api/aois";
import { useDetections } from "../api/detections";
import { useEvents } from "../api/events";
import type { EventRow } from "../api/types";
import { polygonCentroid } from "../lib/geo";
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
  const requestFlyTo = useMapStore((s) => s.requestFlyTo);
  const selectedAoiId = useAoiStore((s) => s.selectedAoiId);
  const setSelectedAoiId = useAoiStore((s) => s.setSelectedAoiId);
  const activeAnalysisId = useAnalysisStore((s) => s.activeAnalysisId);
  const setInspectorTarget = useAnalysisStore((s) => s.setInspectorTarget);
  const setActiveAnalysisId = useAnalysisStore((s) => s.setActiveAnalysisId);
  const setChangeVisible = useAnalysisStore((s) => s.setChangeVisible);

  const { data: aois } = useAois();
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

  const jobInProgress =
    activeAnalysis && (activeAnalysis.status === "pending" || activeAnalysis.status === "running");
  // A job stuck pending/running past the stall deadline (see analysisIsStalled)
  // has stopped being polled — surface that as a terminal STALLED state rather
  // than an indeterminate bar that animates forever with no job behind it.
  const jobStalled = analysisIsStalled(activeAnalysis);

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
      // BRIEF v2, found for real (two rounds): (1) this only ever set
      // inspectorTarget, so MapCanvas's Change layer (keyed off
      // activeAnalysisId, not inspectorTarget) never had anything to
      // render for a PAST analysis -- toggling "Change" after clicking an
      // old result went dark. (2) even after fixing that, clicking a
      // result still looked like it "did nothing": nothing here ever
      // selected the analysis's OWN aoi_id or moved the map, so unless you
      // already happened to have that exact AOI selected, the only visible
      // effect was the easy-to-miss Inspector panel updating -- the map,
      // AOI panel, and timeline all stayed exactly as they were. Now
      // selects and flies to the analysis's AOI too, same as clicking an
      // AOI row directly.
      onClick: () => {
        setInspectorTarget({ kind: "analysis", id: analysis.id });
        setActiveAnalysisId(analysis.id);
        // Clicking a change result should actually SHOW the change — the
        // overlay is its own toggle now (decoupled from the base imagery), so
        // turn it on rather than making the user hunt for the Change switch.
        setChangeVisible(true);
        const aoi = aois?.find((a) => a.id === analysis.aoi_id);
        if (aoi) {
          setSelectedAoiId(aoi.id);
          const { longitude, latitude } = polygonCentroid(aoi.geometry);
          requestFlyTo({ longitude, latitude, zoom: 12 });
        }
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
      {jobInProgress && (
        <div className={jobStalled ? "job-card stalled" : "job-card"}>
          <div className="job-card-header">
            <span className="job-card-name">
              CHANGE DETECTION · {jobStalled ? "STALLED" : activeAnalysis.status.toUpperCase()}
            </span>
          </div>
          {jobStalled ? (
            <div className="job-card-note">
              no worker response after 5 min — the job is still queued. check the change-detection worker is running.
            </div>
          ) : (
            <div className="job-card-track">
              <div className="job-card-fill indeterminate" />
            </div>
          )}
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
