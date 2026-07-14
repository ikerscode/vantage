import { useEffect, useRef, useState } from "react";

import { useAois, useArchiveAoi, useCreateAoi } from "../api/aois";
import { polygonAreaKm2, polygonCentroid } from "../lib/geo";
import { useAnalysisStore } from "../store/analysisStore";
import { useAoiStore } from "../store/aoiStore";
import { useMapStore } from "../store/mapStore";
import { pushErrorToast } from "../store/toastStore";

// Mirrors the backend's MAX_AOI_AREA_KM2 (apps/api/app/schemas/geo.py) so a
// too-big polygon is rejected before it's even sent. BRIEF v2, found for
// real: with no basemap for scale, a user zoomed out to Z1 drew a
// 32.5-million-km² AOI (half of Africa) without realizing it -- the imagery
// search for it matched millions of scenes and hung the UI forever. A
// fresh backend rejects it at creation too, but an install running older
// backend images doesn't -- and either way a clear message here beats a
// bare 422.
const MAX_AOI_AREA_KM2 = 50_000;

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
  // Sensor this AOI will be tracked with — fixed for its lifetime once saved
  // (see apps/api/app/imagery/sensor.py). Defaults to optical since that's
  // the backend's own default and the far more common case.
  const [draftCollection, setDraftCollection] = useState<"sentinel-2-l2a" | "sentinel-1-grd">(
    "sentinel-2-l2a",
  );

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
    // instant: this is the first paint — jump straight to the AOI rather than
    // animating a multi-second fly across the empty void to get there.
    requestFlyTo({ longitude, latitude, zoom: 12, instant: true });
  }, [aois, selectedAoiId, setSelectedAoiId, setInspectorTarget, requestFlyTo]);

  const handleSave = () => {
    if (!draftGeometry || !draftName.trim()) return;
    const areaKm2 = polygonAreaKm2(draftGeometry);
    if (areaKm2 > MAX_AOI_AREA_KM2) {
      pushErrorToast(
        `This AOI covers ${Math.round(areaKm2).toLocaleString()} km² — the limit is ` +
          `${MAX_AOI_AREA_KM2.toLocaleString()} km². Zoom in (see the scale bar, bottom right) and draw a smaller area.`,
      );
      return;
    }
    createAoi.mutate(
      { name: draftName.trim(), geometry: draftGeometry, collection: draftCollection },
      {
        // Found while confirming the drawing fix live: a freshly-drawn AOI
        // never got selected, so the map stayed on its dark default view
        // until you separately clicked it in the list -- looked like
        // drawing "didn't do anything visible" right after the save that
        // should have been the payoff. Select + fly to it immediately,
        // same as clicking an existing row does.
        onSuccess: (created) => {
          setDraftGeometry(null);
          setDraftName("");
          setDraftCollection("sentinel-2-l2a");
          setIsDrawing(false);
          setSelectedAoiId(created.id);
          setInspectorTarget({ kind: "aoi", id: created.id });
          const { longitude, latitude } = polygonCentroid(created.geometry);
          requestFlyTo({ longitude, latitude, zoom: 12 });
        },
      },
    );
  };

  const handleCancel = () => {
    setDraftGeometry(null);
    setIsDrawing(false);
    setDraftName("");
    setDraftCollection("sentinel-2-l2a");
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
            style={{ flex: "1 1 100%" }}
            placeholder="AOI name"
            value={draftName}
            onChange={(e) => setDraftName(e.target.value)}
          />
          <div
            className="aoi-sensor-toggle"
            title="Sensor this AOI is tracked with — fixed once saved"
          >
            <button
              className={draftCollection === "sentinel-2-l2a" ? "active" : ""}
              onClick={() => setDraftCollection("sentinel-2-l2a")}
              disabled={createAoi.isPending}
            >
              OPTICAL
            </button>
            <button
              className={draftCollection === "sentinel-1-grd" ? "active" : ""}
              onClick={() => setDraftCollection("sentinel-1-grd")}
              disabled={createAoi.isPending}
            >
              SAR
            </button>
          </div>
          <button
            className={createAoi.isPending ? "tag btn-busy" : "tag"}
            onClick={handleSave}
            disabled={createAoi.isPending}
          >
            {createAoi.isPending ? (
              <>
                <span className="spinner" />
                SAVING…
              </>
            ) : (
              "SAVE"
            )}
          </button>
          <button className="tag" onClick={handleCancel} disabled={createAoi.isPending}>
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
                <div className={active ? "row-bar row-bar-active" : "row-bar"} />
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
                  disabled={archiveAoi.isPending}
                  onClick={(e) => {
                    e.stopPropagation();
                    archiveAoi.mutate(aoi.id);
                  }}
                >
                  {archiveAoi.isPending && archiveAoi.variables === aoi.id ? (
                    <span className="spinner" />
                  ) : (
                    "×"
                  )}
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
