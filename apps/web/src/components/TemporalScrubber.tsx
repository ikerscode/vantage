import { useEffect, useRef, useState } from "react";

import { useAnalyses, useCreateAnalysis } from "../api/analyses";
import { useAois } from "../api/aois";
import { useStacScenes } from "../api/stac";
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

// User-resizable timeline panel height (drag the handle on its top edge).
// Persisted across sessions: the first thing anyone does with a resize
// handle is set it once to their preference and never think about it again,
// so re-defaulting on every reload would be a small but real annoyance.
const SCRUBBER_HEIGHT_STORAGE_KEY = "vantage.scrubberHeightPx";
const SCRUBBER_MIN_HEIGHT = 44;
const SCRUBBER_MAX_HEIGHT = 420;
// 60px (from the previous ~50% shrink) + 35%, per direct follow-up feedback.
const SCRUBBER_DEFAULT_HEIGHT = 81;

function clampScrubberHeight(value: number): number {
  return Math.min(SCRUBBER_MAX_HEIGHT, Math.max(SCRUBBER_MIN_HEIGHT, value));
}

function loadStoredScrubberHeight(): number {
  if (typeof window === "undefined") return SCRUBBER_DEFAULT_HEIGHT;
  const stored = Number(window.localStorage.getItem(SCRUBBER_HEIGHT_STORAGE_KEY));
  return Number.isFinite(stored) && stored > 0 ? clampScrubberHeight(stored) : SCRUBBER_DEFAULT_HEIGHT;
}

export function TemporalScrubber() {
  const mode = useMapStore((s) => s.mode);
  const selectedAoiId = useAoiStore((s) => s.selectedAoiId);
  const { data: aois } = useAois();
  const selectedAoi = aois?.find((a) => a.id === selectedAoiId);

  // 24 months, not 3 (BRIEF v1.8, found for real on a fresh install): the
  // bundled demo scenes are ~several months to a year+ old by the time
  // anyone actually installs this app, and with no auto-search/auto-pick
  // (below) either, a 3-month default window silently found nothing,
  // ever, until a user happened to know to widen it themselves — which
  // looked identical to a rendering bug (the map has no basemap, so "no
  // scene selected" and "imagery failed to load" both show as solid
  // black/flat color).
  const [dateFrom, setDateFrom] = useState(() => monthsAgoIso(24));
  const [dateTo, setDateTo] = useState(() => todayIso());

  const [scrubberHeight, setScrubberHeight] = useState(loadStoredScrubberHeight);

  // Drag-to-resize (top edge handle). startY/startHeight are captured once
  // per gesture in this closure (not in component state), so the move/up
  // listeners added here are the exact same function references removed on
  // mouseup, regardless of how many re-renders (from setScrubberHeight
  // itself) happen mid-drag.
  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault();
    const startY = e.clientY;
    const startHeight = scrubberHeight;

    const handleMove = (moveEvent: MouseEvent) => {
      // Dragging UP shrinks clientY, which should GROW the panel, since it's
      // anchored to the bottom of the screen, so "up" means "taller".
      setScrubberHeight(clampScrubberHeight(startHeight + (startY - moveEvent.clientY)));
    };
    const handleUp = () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
      setScrubberHeight((h) => {
        window.localStorage.setItem(SCRUBBER_HEIGHT_STORAGE_KEY, String(h));
        return h;
      });
    };
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
  };

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
  const setChangeVisible = useAnalysisStore((s) => s.setChangeVisible);

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

  // Keyed by AOI + date range: fires automatically on AOI selection and on any
  // date-range change, and — crucially — never carries another AOI's results
  // over (see api/stac.ts's useStacScenes for the "no imagery until reload"
  // bug this replaced). No manual auto-search effect needed anymore.
  const scenesQuery = useStacScenes(
    selectedAoiId
      ? {
          aoi_id: selectedAoiId,
          date_from: dateFrom,
          date_to: dateTo,
          // Search the AOI's own sensor collection (optical vs SAR). Before
          // this, every AOI searched the backend's global optical default
          // regardless of what it was actually tracked against, so a SAR AOI
          // would only ever turn up sentinel-2-l2a results (or none).
          collections: selectedAoi ? [selectedAoi.collection] : undefined,
        }
      : null,
  );
  const scenes = scenesQuery.data ?? [];

  const handleSearch = () => {
    if (!selectedAoiId) return;
    void scenesQuery.refetch();
  };

  const handleRunAnalysis = () => {
    if (!selectedAoiId || !dateA || !dateB) return;
    createAnalysis.mutate(
      { aoi_id: selectedAoiId, date_a: dateA, date_b: dateB },
      {
        onSuccess: (analysis) => {
          setActiveAnalysisId(analysis.id);
          // Surface the change overlay so the result is visible the moment the
          // job completes (it stacks on top of the base imagery, which stays on).
          setChangeVisible(true);
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

  // Populates singleDate (Explore) AND dateA/dateB (Analyze) together, from
  // whichever scenes exist, regardless of which scrubberMode is currently
  // active — switching modes should never land on an empty, unusable
  // state. Found for real: "RUN ANALYSIS" looked completely broken
  // (clicking it did nothing) because nothing had ever set dateA/dateB —
  // handleRunAnalysis silently no-ops without both, and picking two
  // distinct scene ticks by hand was the only way to populate them.
  const autoPickedForAoi = useRef<string | null>(null);
  useEffect(() => {
    if (!selectedAoiId || scenes.length === 0 || autoPickedForAoi.current === selectedAoiId) return;
    autoPickedForAoi.current = selectedAoiId;

    const sorted = [...scenes].sort((a, b) => a.datetime.localeCompare(b.datetime));
    const earliest = sorted[0];
    const latest = sorted[sorted.length - 1];

    setSelectedScene(latest);
    if (!singleDate) setSingleDate(latest.datetime.slice(0, 10));
    if (!dateA && !dateB) {
      setDateA(earliest.datetime.slice(0, 10));
      // A single-scene AOI has nothing to compare against yet — dateB
      // stays null (RUN ANALYSIS correctly stays disabled) rather than
      // comparing a date against itself.
      if (earliest.id !== latest.id) setDateB(latest.datetime.slice(0, 10));
    }
    // Deliberately excludes singleDate/dateA/dateB/setters/pickScene — this
    // is a one-shot default per AOI, not a live sync; re-running it on
    // every dependency change would fight a user's own scene choice.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAoiId, scenes]);

  if (mode === "monitor") {
    const analyses = recentAnalyses ?? [];
    const since = analyses.length ? analyses[analyses.length - 1].created_at.slice(0, 10) : monthsAgoIso(1);
    const now = todayIso();
    return (
      <div className="panel scrubber" style={{ height: scrubberHeight }}>
        <div className="scrubber-resize-handle" onMouseDown={handleResizeStart} title="Drag to resize" />
        <div className="scrubber-body">
          {/* key={mode}: forces a real remount when switching Explore/Analyze
              <-> Monitor (see styles.css's .scrubber-header comment). Without
              it, React reconciles this same div in place across the branch
              swap below and the pop-in animation would only ever fire once,
              on first mount. */}
          <div className="scrubber-header" key={mode}>
            <span className="scrubber-title">Timeline</span>
            <span className="status-value">Monitoring · live</span>
            {selectedAoiId && <span className="status-value-tertiary">watching AOI since {since}</span>}
          </div>
          <div className="scrubber-axis" key={mode}>
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
      </div>
    );
  }

  return (
    <div className="panel scrubber" style={{ height: scrubberHeight }}>
      <div className="scrubber-resize-handle" onMouseDown={handleResizeStart} title="Drag to resize" />
      <div className="scrubber-body">
        <div className="scrubber-header" key={mode}>
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
            <button
              className={scenesQuery.isFetching ? "tag btn-busy" : "tag"}
              onClick={handleSearch}
              disabled={!selectedAoiId || scenesQuery.isFetching}
            >
              {scenesQuery.isFetching ? (
                <>
                  <span className="spinner" />
                  SEARCHING…
                </>
              ) : (
                "SEARCH"
              )}
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

        <div className="scrubber-axis" key={mode}>
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
          <button
            className={createAnalysis.isPending ? "tag btn-busy" : "tag"}
            onClick={handleRunAnalysis}
            disabled={!dateA || !dateB || createAnalysis.isPending}
          >
            {createAnalysis.isPending ? (
              <>
                <span className="spinner" />
                SUBMITTING…
              </>
            ) : (
              "RUN ANALYSIS"
            )}
          </button>
        )}
      </div>
    </div>
  );
}
