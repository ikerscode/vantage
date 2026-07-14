// Mirrors apps/api/app/imagery/sensor.py's collection -> sensor dispatch —
// keep in sync with the backend contract. Drives which base layers
// (True Color/NDVI vs SAR Amplitude/False Color) and which overlays
// (Detections is optical-only) a given AOI's collection offers in the UI.

export type SensorType = "optical" | "sar";

const SAR_COLLECTIONS = new Set(["sentinel-1-grd"]);

export function sensorForCollection(collection: string | undefined | null): SensorType {
  if (collection && SAR_COLLECTIONS.has(collection)) return "sar";
  // Falls back to "optical" for anything else (including undefined, while an
  // AOI is still loading) rather than throwing — the backend's AOICreate
  // validator is the actual enforcement point (app/schemas/aoi.py); a stray
  // unrecognized value reaching the map should degrade gracefully, not crash
  // the whole view.
  return "optical";
}
