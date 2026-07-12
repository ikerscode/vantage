import { useEffect, useState } from "react";

import { useAois } from "../api/aois";
import { latLonToMGRS } from "../lib/mgrs";
import { getRuntimeConfig } from "../lib/runtimeConfig";
import { scaleBarLabel } from "../lib/scaleBar";
import { useMonitorAlertStatus } from "../lib/monitorAlerts";
import { useAnalysisStore } from "../store/analysisStore";
import { useAoiStore } from "../store/aoiStore";
import { useEventStreamStore } from "../store/eventStreamStore";
import { useMapStore } from "../store/mapStore";

function useZuluClock(): string {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}:${pad(now.getUTCSeconds())}Z`;
}

export function StatusStrip() {
  const zulu = useZuluClock();
  const cursorLatLon = useMapStore((s) => s.cursorLatLon);
  const viewState = useMapStore((s) => s.viewState);

  const { data: aois } = useAois();
  const selectedAoiId = useAoiStore((s) => s.selectedAoiId);
  const selectedAoi = aois?.find((a) => a.id === selectedAoiId);

  const selectedScene = useAnalysisStore((s) => s.selectedScene);
  const sseStatus = useEventStreamStore((s) => s.status);
  const { isAnyAlert, alertMonitors } = useMonitorAlertStatus();
  // Only set when running inside the desktop launcher (BRIEF v1.3 §11:
  // "version stamp visible in-app") — plain docker-compose deployments have
  // no single meaningful build version, so this segment just doesn't render.
  const appVersion = getRuntimeConfig().appVersion;

  const curText = cursorLatLon
    ? `${Math.abs(cursorLatLon.lat).toFixed(4)}°${cursorLatLon.lat >= 0 ? "N" : "S"} ${Math.abs(cursorLatLon.lon).toFixed(4)}°${cursorLatLon.lon >= 0 ? "E" : "W"}`
    : "—";

  // MGRS grid of the cursor (falls back to the map centre when the pointer is
  // off the map) — the coordinate frame NATO/allied forces actually operate in.
  const gridLat = cursorLatLon?.lat ?? viewState.latitude;
  const gridLon = cursorLatLon?.lon ?? viewState.longitude;
  const mgrs = latLonToMGRS(gridLat, gridLon) ?? "OUT OF UTM";

  return (
    <div className={isAnyAlert ? "panel status-strip alert-active" : "panel status-strip"}>
      <div className="status-segment">
        <span className="status-label">CUR</span>
        <span className="status-value">{curText}</span>
      </div>
      <div className="status-divider" />
      <div className="status-segment">
        <span className="status-label">GRID</span>
        <span className="status-value-accent" title="Military Grid Reference System (WGS84)">{mgrs}</span>
      </div>
      <div className="status-divider" />
      <div className="status-segment">
        <span className="status-label">UTC</span>
        <span className="status-value-accent">{zulu}</span>
      </div>
      <div className="status-divider" />
      {isAnyAlert ? (
        <div className="status-alert-chip">
          <span className="status-dot" />
          <span className="status-alert-chip-label">
            ALERT ·{" "}
            {alertMonitors.length === 1
              ? (aois?.find((a) => a.id === alertMonitors[0].aoi_id)?.name ?? alertMonitors[0].aoi_id.slice(0, 8))
              : `${alertMonitors.length} MONITORS`}
          </span>
        </div>
      ) : (
        <div className="status-segment">
          <span className="status-label">AOI</span>
          <span className="status-value">{selectedAoi ? selectedAoi.name : "—"}</span>
        </div>
      )}
      <div className="status-divider" />
      <div className="status-segment">
        <span className="status-label">SCENE</span>
        <span className="status-value-dim">
          {selectedScene ? selectedScene.datetime.slice(0, 16).replace("T", " ") + "Z" : "—"}
        </span>
        {selectedScene && (
          <span className="status-value-tertiary">
            CLD {selectedScene.cloud_cover != null ? selectedScene.cloud_cover.toFixed(0) : "?"}%
          </span>
        )}
      </div>
      <div className="status-divider" />
      <div className="status-segment">
        <span className={sseStatus === "open" ? "status-dot status-dot-nominal" : "status-dot status-dot-down"} />
        <span className="status-label">LIVE</span>
        <span className="status-value-tertiary">{sseStatus === "open" ? "SSE·OK" : "SSE·DOWN"}</span>
      </div>
      <div className="status-scale-group">
        <div className="status-segment">
          <div className="status-scale-bar" />
          <span className="status-value-dim">{scaleBarLabel(viewState.latitude, viewState.zoom)}</span>
        </div>
        <span className="status-value-tertiary">Z{Math.round(viewState.zoom)}</span>
      </div>
      {appVersion && (
        <>
          <div className="status-divider" />
          <span className="status-value-tertiary">v{appVersion}</span>
        </>
      )}
    </div>
  );
}
