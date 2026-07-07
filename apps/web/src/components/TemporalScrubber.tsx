import { useEffect, useState } from "react";

import { useAnalyses, useCreateAnalysis } from "../api/analyses";
import { useStacSearch } from "../api/stac";
import type { StacItemSummary } from "../api/types";
import { useMonitorAlertStatus } from "../lib/monitorAlerts";
import { useAnalysisStore } from "../store/analysisStore";
import { useAoiStore } from "../store/aoiStore";
import { useMapStore } from "../store/mapStore";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function monthsAgoIso(months: number): string {
  const d = new Date();
  d.setMonth(d.getMonth() - months);
  return d.toISOString().slice(0, 10);
}

function dateToTime(iso: string): number {
  return new Date(iso).getTime();
}

/** % position of a scene's date within [from, to], clamped to the axis. */
function tickPosition(sceneDate: string, from: string, to: string): number {
  const span = dateToTime(to) - dateToTime(from);
  if (span <= 0) return 50;
  const pos = ((dateToTime(sceneDate) - dateToTime(from)) / span) * 100;
  return Math.min(100, Math.max(0, pos));
}

export function TemporalScrubber() {
  const mode = useMapStore((s) => s.mode);
  const selectedAoiId = useAoiStore((s) => s.selectedAoiId);
  const stacSearch = useStacSearch();

  const [dateFrom, setDateFrom] = useState(() => monthsAgoIso(3));
  const [dateTo, setDateTo] = useState(() => todayIso());

  const scrubberMode = useAnalysisStore((s) => s.scrubberMode);
  const setScrubberMode = useAnalysisStore((s) => s.setScrubberMode);
  const singleDate = useAnalysisStore((s) => s.singleDate);
  const setSingleDate = useAnalysisStore((s) => s.setSingleDate);
  const setSelectedScene = useAnalysisStore((s) => s.setSelectedScene);
  const dateA = useAnalysisStore((s) => s.dateA);
  const dateB = useAnalysisStore((s) => s.dateB);
  const setDateA = useAnalysisStore((s) => s.setDateA);
  const setDateB = useAnalysisStore((s) => s.setDateB);
  const setActiveAnalysisId = useAnalysisStore((s) => s.setActiveAnalysisId);
  const setInspectorTarget = useAnalysisStore((s) => s.setInspectorTarget);

  const createAnalysis = useCreateAnalysis();
  const { data: recentAnalyses } = useAnalyses(mode === "monitor" ? (selectedAoiId ?? undefined) : undefined);
  const { alertMonitorIds, monitors } = useMonitorAlertStatus();
  const aoiIsAlert = monitors.some((m) => m.aoi_id === selectedAoiId && alertMonitorIds.has(m.id));

  // Default the scrubber's own single/before-after toggle to match the mode
  // you just switched to — still user-overridable from the toggle itself.
  useEffect(() => {
    if (mode === "explore") setScrubberMode("single");
    else if (mode === "analyze") setScrubberMode("before-after");
  }, [mode, setScrubberMode]);

  const scenes = stacSearch.data ?? [];

  const handleSearch = () => {
    if (!selectedAoiId) return;
    stacSearch.mutate({ aoi_id: selectedAoiId, date_from: dateFrom, date_to: dateTo });
  };

  const handleRunAnalysis = () => {
    if (!selectedAoiId || !dateA || !dateB) return;
    createAnalysis.mutate(
      { aoi_id: selectedAoiId, date_a: dateA, date_b: dateB },
      {
        onSuccess: (analysis) => {
          setActiveAnalysisId(analysis.id);
          setInspectorTarget({ kind: "analysis", id: analysis.id });
        },
      },
    );
  };

  const pickScene = (scene: StacItemSummary) => {
    const dateStr = scene.datetime.slice(0, 10);
    setSelectedScene(scene);
    if (scrubberMode === "single") {
      setSingleDate(dateStr);
    } else if (!dateA || (dateB && dateStr !== dateA)) {
      setDateA(dateStr);
      setDateB(null);
    } else if (dateStr !== dateA) {
      setDateB(dateStr);
    }
  };

  if (mode === "monitor") {
    const analyses = recentAnalyses ?? [];
    const since = analyses.length ? analyses[analyses.length - 1].created_at.slice(0, 10) : monthsAgoIso(1);
    const now = todayIso();
    return (
      <div className="panel scrubber">
        <div className="scrubber-header">
          <span className="scrubber-title">Timeline</span>
          <span className="status-value">Monitoring · live</span>
          {selectedAoiId && <span className="status-value-tertiary">watching AOI since {since}</span>}
        </div>
        <div className="scrubber-axis">
          <div className="scrubber-baseline" />
          {analyses.map((a) => (
            <div
              key={a.id}
              className="scrubber-watch-dot"
              style={{ left: `${tickPosition(a.created_at, since, now)}%` }}
              title={`${a.date_a} → ${a.date_b}: ${a.status}`}
            />
          ))}
          <div className={aoiIsAlert ? "scrubber-now-marker alert" : "scrubber-now-marker"} />
          <span
            className={aoiIsAlert ? "scrubber-handle-label alert" : "scrubber-handle-label accent"}
            style={{ right: 0, left: "auto", transform: "translateX(50%)" }}
          >
            NOW
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="panel scrubber">
      <div className="scrubber-header">
        <span className="scrubber-title">Timeline</span>
        {scrubberMode === "single" ? (
          <span className="status-value">{singleDate ?? "no date selected"}</span>
        ) : (
          <span className="status-value">
            {dateA ?? "before"} → {dateB ?? "after"}
          </span>
        )}
        <span className="status-value-tertiary">{scenes.length} scene(s) in range</span>
        <div className="scrubber-search-row">
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          <span className="status-value-tertiary">→</span>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          <button className="tag" onClick={handleSearch} disabled={!selectedAoiId || stacSearch.isPending}>
            SEARCH
          </button>
        </div>
        <div className="scrubber-mode-toggle">
          <button className={scrubberMode === "single" ? "active" : ""} onClick={() => setScrubberMode("single")}>
            SINGLE
          </button>
          <button
            className={scrubberMode === "before-after" ? "active" : ""}
            onClick={() => setScrubberMode("before-after")}
          >
            BEFORE / AFTER
          </button>
        </div>
      </div>

      {!selectedAoiId && <span className="status-value-tertiary">select an AOI first</span>}

      <div className="scrubber-axis">
        <div className="scrubber-baseline" />
        {scenes.map((scene) => {
          const dateStr = scene.datetime.slice(0, 10);
          const pos = tickPosition(dateStr, dateFrom, dateTo);
          const tall = (scene.cloud_cover ?? 0) < 20;
          return (
            <div
              key={scene.id}
              className="scrubber-tick-hit"
              style={{ left: `${pos}%` }}
              title={`${dateStr} · cloud ${scene.cloud_cover?.toFixed(0) ?? "?"}%`}
              onClick={() => pickScene(scene)}
            >
              <div
                className="scrubber-tick"
                style={{ left: 4, height: tall ? 11 : 5, opacity: tall ? 0.5 : 0.28 }}
              />
            </div>
          );
        })}

        {scrubberMode === "single" && singleDate && (
          <>
            <div className="scrubber-handle single" style={{ left: `${tickPosition(singleDate, dateFrom, dateTo)}%` }} />
            <span
              className="scrubber-handle-label accent"
              style={{ left: `${tickPosition(singleDate, dateFrom, dateTo)}%` }}
            >
              {singleDate}
            </span>
          </>
        )}

        {scrubberMode === "before-after" && (
          <>
            {dateA && dateB && (
              <div
                className="scrubber-span"
                style={{
                  left: `${Math.min(tickPosition(dateA, dateFrom, dateTo), tickPosition(dateB, dateFrom, dateTo))}%`,
                  width: `${Math.abs(tickPosition(dateB, dateFrom, dateTo) - tickPosition(dateA, dateFrom, dateTo))}%`,
                }}
              />
            )}
            {dateA && (
              <>
                <div className="scrubber-handle before" style={{ left: `${tickPosition(dateA, dateFrom, dateTo)}%` }} />
                <span className="scrubber-handle-label" style={{ left: `${tickPosition(dateA, dateFrom, dateTo)}%` }}>
                  {dateA}
                </span>
              </>
            )}
            {dateB && (
              <>
                <div className="scrubber-handle after" style={{ left: `${tickPosition(dateB, dateFrom, dateTo)}%` }} />
                <span
                  className="scrubber-handle-label accent"
                  style={{ left: `${tickPosition(dateB, dateFrom, dateTo)}%` }}
                >
                  {dateB}
                </span>
              </>
            )}
          </>
        )}
      </div>

      {mode === "analyze" && (
        <button className="tag" onClick={handleRunAnalysis} disabled={!dateA || !dateB || createAnalysis.isPending}>
          {createAnalysis.isPending ? "SUBMITTING…" : "RUN ANALYSIS"}
        </button>
      )}
    </div>
  );
}
