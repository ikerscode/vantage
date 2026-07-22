import type { CSSProperties } from "react";

import { useAois } from "../api/aois";
import { useInferenceStatus } from "../api/inference";
import { sensorForCollection } from "../lib/sensor";
import { type BaseRasterLayerId, useAnalysisStore } from "../store/analysisStore";
import { useAoiStore } from "../store/aoiStore";

// True Color / NDVI are the mutually-exclusive optical base imagery; SAR
// Amplitude / False Color are the equivalent pair for a SAR AOI (see
// lib/sensor.ts) — an AOI only ever offers one pair, never all four, since
// its collection is fixed at creation. Change and Detections are overlays
// that stack on top of whichever base is showing, so selecting them never
// blanks the imagery underneath.
const OPTICAL_BASE_LAYERS: { id: BaseRasterLayerId; name: string }[] = [
  { id: "true_color", name: "True Color" },
  { id: "ndvi", name: "NDVI" },
];
const SAR_BASE_LAYERS: { id: BaseRasterLayerId; name: string }[] = [
  { id: "sar_amplitude", name: "SAR Amplitude" },
  { id: "sar_false_color", name: "SAR False Color" },
];

export function LayersControl() {
  const { data: aois } = useAois();
  const selectedAoiId = useAoiStore((s) => s.selectedAoiId);
  const selectedAoi = aois?.find((a) => a.id === selectedAoiId);
  const sensor = sensorForCollection(selectedAoi?.collection);
  const isSar = sensor === "sar";

  const activeRasterLayer = useAnalysisStore((s) => s.activeRasterLayer);
  const setActiveRasterLayer = useAnalysisStore((s) => s.setActiveRasterLayer);
  const rasterOpacity = useAnalysisStore((s) => s.rasterOpacity);
  const setRasterOpacity = useAnalysisStore((s) => s.setRasterOpacity);
  const changeVisible = useAnalysisStore((s) => s.changeVisible);
  const toggleChangeVisible = useAnalysisStore((s) => s.toggleChangeVisible);
  const detectionsVisible = useAnalysisStore((s) => s.detectionsVisible);
  const toggleDetectionsVisible = useAnalysisStore((s) => s.toggleDetectionsVisible);
  const { data: inferenceStatus } = useInferenceStatus();

  const baseLayers = isSar ? SAR_BASE_LAYERS : OPTICAL_BASE_LAYERS;
  // Base is always live (1); overlays add to the count when on. Detections
  // can't be live for a SAR AOI (see the honest-seam note below), so it's
  // excluded from the count there even if the toggle was left on from a
  // previously-selected optical AOI.
  const liveCount =
    1 + (changeVisible ? 1 : 0) + (detectionsVisible && !isSar ? 1 : 0);

  return (
    <div className="panel">
      <div className="panel-header">
        <h2 className="panel-title">Layers</h2>
        <span className="panel-header-meta">
          {liveCount} LIVE
        </span>
      </div>

      {baseLayers.map((layer) => {
        const on = activeRasterLayer === layer.id;
        const opacity = rasterOpacity[layer.id];
        return (
          <div className="layer-row" key={layer.id}>
            <button
              className={on ? "switch on" : "switch"}
              onClick={() => setActiveRasterLayer(layer.id)}
              title={
                isSar
                  ? "Base imagery — SAR Amplitude and False Color are mutually exclusive; one is always on"
                  : "Base imagery — True Color and NDVI are mutually exclusive; one is always on"
              }
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
          Rendered as a pulsing orange footprint over the changed pixels.
          Works identically for both sensors (NDVI-diff or SAR log-ratio dB —
          see app/imagery/sensor.py), so this row never changes with isSar. */}
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
          className={detectionsVisible && !isSar ? "switch on" : "switch"}
          onClick={toggleDetectionsVisible}
          disabled={isSar}
          title={
            isSar
              ? "Object detection isn't available for SAR AOIs yet"
              : "Object detections from the active analysis (pulsing red outlines)"
          }
        >
          <span className="switch-knob" />
        </button>
        <span className={detectionsVisible && !isSar ? "layer-name on" : "layer-name"}>Detections</span>
        <span className="layer-tag alert">VEC</span>
        <div className="layer-opacity-track">
          <div
            className={detectionsVisible && !isSar ? "layer-opacity-fill on" : "layer-opacity-fill"}
            style={{ width: detectionsVisible && !isSar ? "100%" : "0%" }}
          />
        </div>
        <span className="layer-opacity-value">{detectionsVisible && !isSar ? "100%" : "0%"}</span>
      </div>

      {/* Honest seam (CLAUDE.md §3): no trained SAR detector exists yet (see
          apps/api/app/services/detection_pipeline.py's module docstring) —
          say so plainly and disable the toggle, rather than let a control
          that can never do anything sit there implying it might. */}
      {isSar && (
        <div className="layer-note">
          Object detection isn't available for SAR AOIs — no detector has been
          trained on SAR amplitude imagery yet. Optical AOIs only.
        </div>
      )}

      {/* Honest seam (CLAUDE.md §3): describe the detector the inference
          service REPORTS it's running (see api/inference.ts), not a hardcoded
          assumption. Found live: this note used to unconditionally describe
          the COCO placeholder and kept doing so after the deployment had been
          switched to the fine-tuned vessel backend — exactly the config-drift
          lie the honest-seams rule exists to prevent. Renders nothing until
          the status query resolves rather than flashing a wrong description. */}
      {!isSar && detectionsVisible && inferenceStatus && (
        <div className="layer-note">
          {!inferenceStatus.reachable
            ? "Inference service unreachable — object detection will fail until it's back up."
            : inferenceStatus.model_backend === "torchvision_fasterrcnn_vessel"
              ? "Vessel detector (fine-tuned for Sentinel-2) — finds vessels only; other object classes aren't detected."
              : "Generic placeholder detector (COCO classes) — expected to find little or nothing on satellite imagery. Set MODEL_BACKEND=torchvision_fasterrcnn_vessel for the maritime detector."}
        </div>
      )}
    </div>
  );
}
