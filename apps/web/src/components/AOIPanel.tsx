import { useEffect, useRef, useState } from "react";

import { useAois, useArchiveAoi, useCreateAoi } from "../api/aois";
import { polygonAreaKm2, polygonCentroid } from "../lib/geo";
import { useAnalysisStore } from "../store/analysisStore";
import { useAoiStore } from "../store/aoiStore";
import { useMapStore } from "../store/mapStore";

export function AOIPanel() {
  const { data: aois, isLoading } = useAois();
  const createAoi = useCreateAoi();
  const archiveAoi = useArchiveAoi();

  const selectedAoiId = useAoiStore((s) => s.selectedAoiId);
  const setSelectedAoiId = useAoiStore((s) => s.setSelectedAoiId);
  const draftGeometry = useAoiStore((s) => s.draftGeometry);
  const setDraftGeometry = useAoiStore((s) => s.setDraftGeometry);
  const isDrawing = useAoiStore((s) => s.isDrawing);
  const setIsDrawing = useAoiStore((s) => s.setIsDrawing);
  const setInspectorTarget = useAnalysisStore((s) => s.setInspectorTarget);
  const setMode = useMapStore((s) => s.setMode);
  const requestFlyTo = useMapStore((s) => s.requestFlyTo);

  const [draftName, setDraftName] = useState("");

  // First-launch UX: INSTALL.md/docs/AIRGAP.md both promise the bundled demo
  // AOI shows real imagery on open, with no manual step — before this, the
  // map had no way to navigate to ANY AOI except a manual coordinate search
  // (found for real: a fresh install genuinely showed nothing but a black
  // map until the user happened to click the AOI row). Auto-selects and
  // flies to the first AOI exactly once per session, only if nothing is
  // already selected — never overrides a user's own subsequent choices.
  const hasAutoNavigated = useRef(false);
  useEffect(() => {
    if (hasAutoNavigated.current || !aois || aois.length === 0 || selectedAoiId !== null) return;
    hasAutoNavigated.current = true;
    const first = aois[0];
    setSelectedAoiId(first.id);
    setInspectorTarget({ kind: "aoi", id: first.id });
    const { longitude, latitude } = polygonCentroid(first.geometry);
    requestFlyTo({ longitude, latitude, zoom: 12 });
  }, [aois, selectedAoiId, setSelectedAoiId, setInspectorTarget, requestFlyTo]);

  const handleSave = () => {
    if (!draftGeometry || !draftName.trim()) return;
    createAoi.mutate(
      { name: draftName.trim(), geometry: draftGeometry },
      {
        onSuccess: () => {
          setDraftGeometry(null);
          setDraftName("");
          setIsDrawing(false);
        },
      },
    );
  };

  const handleCancel = () => {
    setDraftGeometry(null);
    setIsDrawing(false);
    setDraftName("");
  };

  const isEmpty = !isLoading && (aois ?? []).length === 0;

  return (
    <div className="panel aoi-panel">
      <div className="panel-header">
        <h2 className="panel-title">Areas of Interest</h2>
        <div className="panel-header-meta">
          <span>{aois?.length ?? 0}</span>
        </div>
      </div>

      <div className="aoi-draw-row">
        <button
          className={isDrawing ? "aoi-draw-button active" : "aoi-draw-button"}
          onClick={() => setIsDrawing(!isDrawing)}
        >
          <span>＋</span>
          {isDrawing ? "DRAWING… CLICK TO ADD VERTEX" : "DRAW NEW AOI"}
        </button>
      </div>

      {draftGeometry && (
        <div className="aoi-draft-form">
          <input
            className="text-input"
            style={{ flex: 1 }}
            placeholder="AOI name"
            value={draftName}
            onChange={(e) => setDraftName(e.target.value)}
          />
          <button className="tag" onClick={handleSave} disabled={createAoi.isPending}>
            SAVE
          </button>
          <button className="tag" onClick={handleCancel}>
            CANCEL
          </button>
        </div>
      )}

      {isEmpty ? (
        <div className="empty-state">
          <div className="empty-state-glyph" />
          <div>
            <div className="empty-state-title">No AOI defined</div>
            <div className="empty-state-body">Draw an area of interest on the map to begin analysis.</div>
          </div>
          <button className="aoi-draw-button active" style={{ width: "100%" }} onClick={() => setIsDrawing(true)}>
            <span>＋</span>DRAW NEW AOI
          </button>
        </div>
      ) : (
        <ul className="row-list">
          {isLoading && <li className="hint">loading…</li>}
          {(aois ?? []).map((aoi) => {
            const active = aoi.id === selectedAoiId;
            return (
              <li
                key={aoi.id}
                className="row"
                onClick={() => {
                  setSelectedAoiId(aoi.id);
                  setInspectorTarget({ kind: "aoi", id: aoi.id });
                  const { longitude, latitude } = polygonCentroid(aoi.geometry);
                  requestFlyTo({ longitude, latitude, zoom: 12 });
                }}
              >
                <div className="row-bar" style={{ background: active ? "var(--accent)" : "transparent" }} />
                <div className="row-column">
                  <div className="aoi-row-line1">
                    <span className={active ? "aoi-row-name active" : "aoi-row-name"}>{aoi.name}</span>
                    <span className="aoi-row-area">{polygonAreaKm2(aoi.geometry).toFixed(1)} km²</span>
                  </div>
                  <span className="aoi-row-line2">created {aoi.created_at.slice(0, 10)}</span>
                </div>
                <button
                  className="icon-button"
                  title="Archive"
                  onClick={(e) => {
                    e.stopPropagation();
                    archiveAoi.mutate(aoi.id);
                  }}
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <div className="aoi-footer">
        <button
          className="aoi-save-monitor-btn"
          disabled={!selectedAoiId}
          onClick={() => setMode("monitor")}
        >
          SAVE AS MONITOR<span>→</span>
        </button>
      </div>
    </div>
  );
}
