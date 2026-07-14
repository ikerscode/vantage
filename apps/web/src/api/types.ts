// Mirrors apps/api/app/schemas/*.py — keep in sync with the backend contract.

export interface GeoJSONPolygon {
  type: "Polygon";
  coordinates: number[][][];
}

export interface AOI {
  id: string;
  name: string;
  description: string | null;
  geometry: GeoJSONPolygon;
  // STAC collection this AOI is tracked against — "sentinel-2-l2a" (optical)
  // or "sentinel-1-grd" (SAR). Fixed for the AOI's lifetime; see
  // apps/api/app/imagery/sensor.py for the pipeline/UI dispatch this drives.
  collection: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface AssetRef {
  href: string;
  title: string | null;
}

export interface StacItemSummary {
  id: string;
  collection: string;
  datetime: string;
  cloud_cover: number | null;
  bbox: number[];
  assets: Record<string, AssetRef>;
  // Fetchable STAC item JSON URL, used for the tiler's multi-asset NDVI band
  // math (red/nir are separate COG files, unlike "visual").
  self_href: string | null;
}

export type AnalysisStatus = "pending" | "running" | "done" | "failed";

export interface AnalysisResult {
  id: string;
  aoi_id: string;
  monitor_id: string | null;
  date_a: string;
  date_b: string;
  threshold: number;
  status: AnalysisStatus;
  error_message: string | null;
  stats: Record<string, number | null> | null;
  tilejson_url: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface Monitor {
  id: string;
  aoi_id: string;
  schedule: string;
  threshold: number | null;
  active: boolean;
  baseline_date: string | null;
  last_scene_date: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EventRow {
  id: string;
  monitor_id: string;
  aoi_id: string;
  analysis_result_id: string;
  metric_value: number;
  threshold: number;
  summary: string;
  created_at: string;
}

export interface Detection {
  id: string;
  analysis_result_id: string;
  bbox: GeoJSONPolygon;
  label: string;
  score: number;
  chip_s3_key: string;
  created_at: string;
}
