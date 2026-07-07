import { useAnalysis } from "../api/analyses";
import { useAois } from "../api/aois";
import { useDetections } from "../api/detections";
import { useEvents } from "../api/events";
import { useMonitors } from "../api/monitors";
import { useAnalysisStore } from "../store/analysisStore";

export function Inspector() {
  const inspectorTarget = useAnalysisStore((s) => s.inspectorTarget);
  const activeAnalysisId = useAnalysisStore((s) => s.activeAnalysisId);
  const setInspectorTarget = useAnalysisStore((s) => s.setInspectorTarget);

  const { data: aois } = useAois();
  const { data: monitors } = useMonitors();
  const { data: events } = useEvents();
  const { data: analysis } = useAnalysis(
    inspectorTarget?.kind === "analysis" ? inspectorTarget.id : (activeAnalysisId ?? undefined),
  );
  // No single-detection endpoint exists (only GET /api/detections?analysis_id=),
  // so a clicked detection is looked up from the currently active analysis's
  // already-loaded set — the same data MapCanvas renders as vector boxes.
  const { data: detections } = useDetections(activeAnalysisId ?? undefined);

  if (!inspectorTarget) {
    return (
      <div className="panel inspector">
        <div className="panel-header">
          <h2 className="panel-title">Inspector</h2>
        </div>
        <p className="hint">select a feature to inspect</p>
      </div>
    );
  }

  const detection =
    inspectorTarget.kind === "detection" ? detections?.find((d) => d.id === inspectorTarget.id) : undefined;

  const renderBody = () => {
    switch (inspectorTarget.kind) {
      case "aoi": {
        const aoi = aois?.find((a) => a.id === inspectorTarget.id);
        if (!aoi) return <p className="hint">loading…</p>;
        return (
          <dl className="inspector-fields">
            <dt>NAME</dt>
            <dd>{aoi.name}</dd>
            <dt>CREATED</dt>
            <dd>{aoi.created_at.slice(0, 19).replace("T", " ")}Z</dd>
          </dl>
        );
      }
      case "analysis": {
        if (!analysis) return <p className="hint">loading…</p>;
        return (
          <dl className="inspector-fields">
            <dt>STATUS</dt>
            <dd>{analysis.status.toUpperCase()}</dd>
            <dt>DATES</dt>
            <dd>
              {analysis.date_a} → {analysis.date_b}
            </dd>
            <dt>THRESHOLD</dt>
            <dd>{analysis.threshold}</dd>
            {analysis.stats && (
              <>
                <dt>CHANGED PX</dt>
                <dd>{analysis.stats.changed_pixel_count ?? "—"}</dd>
                <dt>PCT CHANGED</dt>
                <dd>
                  {analysis.stats.pct_changed != null ? `${(analysis.stats.pct_changed * 100).toFixed(1)}%` : "—"}
                </dd>
              </>
            )}
            {analysis.error_message && (
              <>
                <dt>ERROR</dt>
                <dd className="error-text">{analysis.error_message}</dd>
              </>
            )}
          </dl>
        );
      }
      case "monitor": {
        const monitor = monitors?.find((m) => m.id === inspectorTarget.id);
        if (!monitor) return <p className="hint">loading…</p>;
        return (
          <dl className="inspector-fields">
            <dt>SCHEDULE</dt>
            <dd>{monitor.schedule}</dd>
            <dt>ACTIVE</dt>
            <dd>{monitor.active ? "YES" : "NO"}</dd>
            <dt>LAST RUN</dt>
            <dd>{monitor.last_run_at ? monitor.last_run_at.slice(0, 16).replace("T", " ") + "Z" : "never"}</dd>
          </dl>
        );
      }
      case "event": {
        const event = events?.find((e) => e.id === inspectorTarget.id);
        if (!event) return <p className="hint">loading…</p>;
        return (
          <dl className="inspector-fields">
            <dt>SUMMARY</dt>
            <dd>{event.summary}</dd>
            <dt>METRIC</dt>
            <dd>{event.metric_value}</dd>
            <dt>THRESHOLD</dt>
            <dd>{event.threshold}</dd>
            <dt>WHEN</dt>
            <dd>{event.created_at.slice(0, 16).replace("T", " ")}Z</dd>
            <dd style={{ gridColumn: "1 / -1" }}>
              <button
                className="tag"
                onClick={() => setInspectorTarget({ kind: "analysis", id: event.analysis_result_id })}
              >
                VIEW ANALYSIS
              </button>
            </dd>
          </dl>
        );
      }
      case "detection": {
        if (!detection) return <p className="hint">loading…</p>;
        return (
          <dl className="inspector-fields">
            <dt>CAPTURED</dt>
            <dd>{detection.created_at.slice(0, 16).replace("T", " ")}Z</dd>
            <dt>SOURCE</dt>
            <dd>{detection.chip_s3_key}</dd>
          </dl>
        );
      }
      default:
        return null;
    }
  };

  return (
    <div className="panel inspector open">
      <div className="panel-header">
        <h2 className="panel-title">Inspector</h2>
        <button className="icon-button" onClick={() => setInspectorTarget(null)}>
          ×
        </button>
      </div>

      {inspectorTarget.kind === "detection" && (
        <div className="inspector-chip">
          {detection && <div className="inspector-chip-marker" />}
          <div className="inspector-chip-caption">
            {detection ? `CHIP · ${detection.chip_s3_key.split("/").pop()}` : "loading chip…"}
          </div>
        </div>
      )}

      <div className="inspector-body">
        {inspectorTarget.kind === "detection" && detection && (
          <>
            <div className="inspector-title-row">
              <span className="inspector-title">{detection.label}</span>
              <span className="inspector-id">DET · {detection.id.slice(0, 8)}</span>
            </div>
            <div className="inspector-conf-row">
              <span className="inspector-conf-label">CONF</span>
              <div className="inspector-conf-track">
                <div className="inspector-conf-fill" style={{ width: `${detection.score * 100}%` }} />
              </div>
              <span className="inspector-conf-value">{detection.score.toFixed(2)}</span>
            </div>
          </>
        )}
        {renderBody()}
      </div>
    </div>
  );
}
