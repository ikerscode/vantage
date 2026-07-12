import type { CSSProperties } from "react";

import { type BaseRasterLayerId, useAnalysisStore } from "../store/analysisStore";

// True Color / NDVI are the mutually-exclusive base imagery — exactly one is
// always on. Change and Detections are overlays that stack on top of it, so
// selecting them never blanks the imagery underneath.
const BASE_LAYERS: { id: BaseRasterLayerId; name: string }[] = [
  { id: "true_color", name: "True Color" },
  { id: "ndvi", name: "NDVI" },
];

export function LayersControl() {
  const activeRasterLayer = useAnalysisStore((s) => s.activeRasterLayer);
  const setActiveRasterLayer = useAnalysisStore((s) => s.setActiveRasterLayer);
  const rasterOpacity = useAnalysisStore((s) => s.rasterOpacity);
  const setRasterOpacity = useAnalysisStore((s) => s.setRasterOpacity);
  const changeVisible = useAnalysisStore((s) => s.changeVisible);
  const toggleChangeVisible = useAnalysisStore((s) => s.toggleChangeVisible);
  const detectionsVisible = useAnalysisStore((s) => s.detectionsVisible);
  const toggleDetectionsVisible = useAnalysisStore((s) => s.toggleDetectionsVisible);

  // Base is always live (1); overlays add to the count when on.
  const liveCount = 1 + (changeVisible ? 1 : 0) + (detectionsVisible ? 1 : 0);

  return (
    <div className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Layers</h2>
        <span className="panel-header-meta">
          {liveCount} LIVE
        </span>
      </div>

      {BASE_LAYERS.map((layer) => {
        const on = activeRasterLayer === layer.id;
        const opacity = rasterOpacity[layer.id];
        return (
          <div className="layer-row" key={layer.id}>
            <button
              className={on ? "switch on" : "switch"}
              onClick={() => setActiveRasterLayer(layer.id)}
              title="Base imagery — True Color and NDVI are mutually exclusive; one is always on"
            >
              <span className="switch-knob" />
            </button>
            <span className={on ? "layer-name on" : "layer-name"}>{layer.name}</span>
            <span className="layer-tag">RAS</span>
            <input
              type="range"
              className={on ? "opacity-slider on" : "opacity-slider"}
              style={{ "--fill": `${Math.round(opacity * 100)}%` } as CSSProperties}
              min={0}
              max={1}
              step={0.05}
              value={opacity}
              onChange={(e) => setRasterOpacity(layer.id, Number(e.target.value))}
            />
            <span className="layer-opacity-value">{Math.round(opacity * 100)}%</span>
          </div>
        );
      })}

      {/* Change overlay — stacks on top of the base imagery (which stays on).
          Rendered as a pulsing orange footprint over the changed pixels. */}
      <div className="layer-row">
        <button
          className={changeVisible ? "switch on" : "switch"}
          onClick={toggleChangeVisible}
          title="Overlay the change map on top of the base imagery"
        >
          <span className="switch-knob" />
        </button>
        <span className={changeVisible ? "layer-name on" : "layer-name"}>Change</span>
        <span className="layer-tag warn">CHG</span>
        <input
          type="range"
          className={changeVisible ? "opacity-slider on" : "opacity-slider"}
          style={{ "--fill": `${Math.round(rasterOpacity.change * 100)}%` } as CSSProperties}
          min={0}
          max={1}
          step={0.05}
          value={rasterOpacity.change}
          onChange={(e) => setRasterOpacity("change", Number(e.target.value))}
        />
        <span className="layer-opacity-value">{Math.round(rasterOpacity.change * 100)}%</span>
      </div>

      <div className="layer-row">
        <button
          className={detectionsVisible ? "switch on" : "switch"}
          onClick={toggleDetectionsVisible}
          title="Object detections from the active analysis (pulsing red outlines)"
        >
          <span className="switch-knob" />
        </button>
        <span className={detectionsVisible ? "layer-name on" : "layer-name"}>Detections</span>
        <span className="layer-tag alert">VEC</span>
        <div className="layer-opacity-track">
          <div
            className={detectionsVisible ? "layer-opacity-fill on" : "layer-opacity-fill"}
            style={{ width: detectionsVisible ? "100%" : "0%" }}
          />
        </div>
        <span className="layer-opacity-value">{detectionsVisible ? "100%" : "0%"}</span>
      </div>

      {/* Honest seam (CLAUDE.md §3): the bundled detector is a COCO-pretrained
          generic model, not an overhead-imagery one — it essentially never
          fires on 10 m/px satellite chips. Say so rather than let an
          always-empty layer read as a bug. */}
      {detectionsVisible && (
        <div className="layer-note">
          Generic placeholder detector (COCO classes) — expected to find little
          or nothing on satellite imagery. See report for the vessel-model path.
        </div>
      )}
    </div>
  );
}
