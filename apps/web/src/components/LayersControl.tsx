import type { CSSProperties } from "react";

import { type RasterLayerId, useAnalysisStore } from "../store/analysisStore";

const RASTER_LAYERS: { id: RasterLayerId; name: string }[] = [
  { id: "true_color", name: "True Color" },
  { id: "ndvi", name: "NDVI" },
  { id: "change", name: "Change" },
];

export function LayersControl() {
  const activeRasterLayer = useAnalysisStore((s) => s.activeRasterLayer);
  const setActiveRasterLayer = useAnalysisStore((s) => s.setActiveRasterLayer);
  const rasterOpacity = useAnalysisStore((s) => s.rasterOpacity);
  const setRasterOpacity = useAnalysisStore((s) => s.setRasterOpacity);
  const detectionsVisible = useAnalysisStore((s) => s.detectionsVisible);
  const toggleDetectionsVisible = useAnalysisStore((s) => s.toggleDetectionsVisible);

  const liveCount = (activeRasterLayer ? 1 : 0) + (detectionsVisible ? 1 : 0);

  return (
    <div className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Layers</h2>
        <span className="panel-header-meta">
          {liveCount} LIVE
        </span>
      </div>

      {RASTER_LAYERS.map((layer) => {
        const on = activeRasterLayer === layer.id;
        const opacity = rasterOpacity[layer.id];
        return (
          <div className="layer-row" key={layer.id}>
            <button
              className={on ? "switch on" : "switch"}
              onClick={() => setActiveRasterLayer(layer.id)}
              title="Raster layers are mutually exclusive"
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

      <div className="layer-row">
        <button
          className={detectionsVisible ? "switch on" : "switch"}
          onClick={toggleDetectionsVisible}
        >
          <span className="switch-knob" />
        </button>
        <span className={detectionsVisible ? "layer-name on" : "layer-name"}>Detections</span>
        <span className="layer-tag">VEC</span>
        <div className="layer-opacity-track">
          <div
            className={detectionsVisible ? "layer-opacity-fill on" : "layer-opacity-fill"}
            style={{ width: detectionsVisible ? "100%" : "0%" }}
          />
        </div>
        <span className="layer-opacity-value">{detectionsVisible ? "100%" : "0%"}</span>
      </div>
    </div>
  );
}
