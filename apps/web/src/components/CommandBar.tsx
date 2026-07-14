import { useEffect, useRef, useState } from "react";

import { useAois } from "../api/aois";
import { apiFetch } from "../api/client";
import type { GeoJSONPolygon, StacItemSummary } from "../api/types";
import { polygonAreaKm2, polygonCentroid } from "../lib/geo";
import { mgrsToLatLon } from "../lib/mgrs";
import { useAoiStore } from "../store/aoiStore";
import { useAnalysisStore } from "../store/analysisStore";
import { useMapStore } from "../store/mapStore";

// Small bbox around a bare coordinate jump, used only for the "preview
// imagery before drawing an AOI" search below. Big enough to almost always
// land at least one covering Sentinel-2 granule, small enough that the
// search stays cheap. ~0.05° is ~5.5km at the equator (less at higher
// latitudes), well under a single granule's ~110km footprint.
const PREVIEW_BUFFER_DEG = 0.05;

function previewGeometry(lon: number, lat: number): GeoJSONPolygon {
  const d = PREVIEW_BUFFER_DEG;
  return {
    type: "Polygon",
    coordinates: [
      [
        [lon - d, lat - d],
        [lon + d, lat - d],
        [lon + d, lat + d],
        [lon - d, lat + d],
        [lon - d, lat - d],
      ],
    ],
  };
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}
function monthsAgoIso(months: number): string {
  const d = new Date();
  d.setMonth(d.getMonth() - months);
  return d.toISOString().slice(0, 10);
}

interface CoordMatch {
  kind: "coord";
  lat: number;
  lon: number;
  // "MGRS" when entered as a military grid reference, else decimal lat/lon.
  source: "COORD" | "MGRS";
}
interface AoiMatch {
  kind: "aoi";
  id: string;
  name: string;
  areaKm2: number;
  longitude: number;
  latitude: number;
}
type Match = CoordMatch | AoiMatch;

// Accepts "34.92, -44.10" / "34.92 -44.10" / "44.10°E 34.92°N" (order is
// inferred from N/S/E/W suffixes when present, else assumed lat,lon).
function parseCoordinate(raw: string): { lat: number; lon: number } | null {
  const cleaned = raw.replace(/°/g, "").trim();
  const parts = cleaned.split(/[,\s]+/).filter(Boolean);
  if (parts.length !== 2) return null;

  const parsed: { value: number; axis: "lat" | "lon" | null }[] = [];
  for (const part of parts) {
    const m = /^(-?\d+(?:\.\d+)?)\s*([NSEW])?$/i.exec(part);
    if (!m) return null;
    let value = Number(m[1]);
    const suffix = m[2]?.toUpperCase();
    let axis: "lat" | "lon" | null = null;
    if (suffix === "S" || suffix === "N") {
      axis = "lat";
      if (suffix === "S") value = -Math.abs(value);
    } else if (suffix === "E" || suffix === "W") {
      axis = "lon";
      if (suffix === "W") value = -Math.abs(value);
    }
    parsed.push({ value, axis });
  }

  const latEntry = parsed.find((v) => v.axis === "lat");
  const lonEntry = parsed.find((v) => v.axis === "lon");
  const lat = latEntry ? latEntry.value : parsed[0].value;
  const lon = lonEntry ? lonEntry.value : parsed[1].value;
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return { lat, lon };
}

export function CommandBar() {
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const { data: aois } = useAois();
  const setSelectedAoiId = useAoiStore((s) => s.setSelectedAoiId);
  const setInspectorTarget = useAnalysisStore((s) => s.setInspectorTarget);
  const setSelectedScene = useAnalysisStore((s) => s.setSelectedScene);
  const requestFlyTo = useMapStore((s) => s.requestFlyTo);

  // Lets a bare coordinate jump show real imagery before any AOI exists
  // there. An operator sizing up a location to circle should see the ground
  // first, not a black void until they've committed to drawing. Best-effort
  // and silent on failure or empty results: no covering scene (ocean,
  // catalog gap, etc.) just leaves the existing "No imagery loaded"
  // empty-hint showing, which is already the correct rendering of that
  // state. An empty result is an expected outcome much of the time, not a
  // real error, so it isn't worth a toast.
  const previewCoordinate = async (lon: number, lat: number) => {
    try {
      const scenes = await apiFetch<StacItemSummary[]>("/api/stac/search", {
        method: "POST",
        body: JSON.stringify({
          geometry: previewGeometry(lon, lat),
          date_from: monthsAgoIso(24),
          date_to: todayIso(),
          collections: ["sentinel-2-l2a"],
        }),
      });
      if (scenes.length === 0) return;
      const best = [...scenes].sort((a, b) => b.datetime.localeCompare(a.datetime))[0];
      setSelectedScene(best);
    } catch {
      // best-effort preview, see comment above
    }
  };

  // Global ⌘K / Ctrl+K hotkey to focus the bar from anywhere.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const trimmed = query.trim();
  const matches: Match[] = [];
  if (trimmed) {
    // Military grid reference takes precedence (e.g. "18S UJ 2340 0645") —
    // it's the coordinate frame the operator is most likely typing; fall back
    // to decimal lat/lon.
    const grid = mgrsToLatLon(trimmed);
    if (grid) {
      matches.push({ kind: "coord", lat: grid.lat, lon: grid.lon, source: "MGRS" });
    } else {
      const coord = parseCoordinate(trimmed);
      if (coord) matches.push({ kind: "coord", lat: coord.lat, lon: coord.lon, source: "COORD" });
    }
    const lower = trimmed.toLowerCase();
    for (const aoi of aois ?? []) {
      if (aoi.name.toLowerCase().includes(lower)) {
        const centroid = polygonCentroid(aoi.geometry);
        matches.push({
          kind: "aoi",
          id: aoi.id,
          name: aoi.name,
          areaKm2: polygonAreaKm2(aoi.geometry),
          longitude: centroid.longitude,
          latitude: centroid.latitude,
        });
      }
    }
  }
  // No PLACE (geocoded place-name) results: a live geocoding API would be an
  // external-SaaS dependency in the core path, which the air-gap invariant
  // forbids — see CLAUDE.md. TODO(v2): a self-hostable gazetteer/geocoder.

  const jumpTo = (match: Match) => {
    if (match.kind === "coord") {
      requestFlyTo({ longitude: match.lon, latitude: match.lat, zoom: 12 });
      // A bare coordinate jump isn't any saved AOI, so deselect whichever one
      // was previously active so its imagery doesn't stay on screen looking
      // like it belongs to this new location.
      setSelectedAoiId(null);
      setInspectorTarget(null);
      void previewCoordinate(match.lon, match.lat);
    } else {
      setSelectedAoiId(match.id);
      setInspectorTarget({ kind: "aoi", id: match.id });
      requestFlyTo({ longitude: match.longitude, latitude: match.latitude, zoom: 12 });
    }
    setQuery("");
    inputRef.current?.blur();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      setQuery("");
      inputRef.current?.blur();
    } else if (e.key === "Enter" && matches.length > 0) {
      jumpTo(matches[0]);
    }
  };

  const expanded = focused && matches.length > 0;

  return (
    <div className={expanded ? "panel command-bar expanded" : "panel command-bar"}>
      <div className="command-bar-input-row">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="command-bar-icon">
          <circle cx="6" cy="6" r="4.2" stroke="currentColor" strokeWidth="1.3" />
          <line x1="9.2" y1="9.2" x2="12.4" y2="12.4" stroke="currentColor" strokeWidth="1.3" />
        </svg>
        <input
          ref={inputRef}
          className="command-bar-input"
          placeholder="Jump to grid ref, coordinates, or AOI…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setTimeout(() => setFocused(false), 120)}
          onKeyDown={handleKeyDown}
        />
        {!focused && <span className="command-bar-hint">⌘K</span>}
      </div>
      {expanded && (
        <div className="command-bar-results">
          {matches.map((match, i) => (
            <div
              key={match.kind === "coord" ? "coord" : match.id}
              className={i === 0 ? "command-bar-result-row top-match" : "command-bar-result-row"}
              onMouseDown={() => jumpTo(match)}
            >
              <span className="command-bar-kind-chip">{match.kind === "coord" ? match.source : "AOI"}</span>
              {match.kind === "coord" ? (
                <>
                  <span className="command-bar-value-mono">
                    {Math.abs(match.lat).toFixed(4)}°{match.lat >= 0 ? "N" : "S"}{" "}
                    {Math.abs(match.lon).toFixed(4)}°{match.lon >= 0 ? "E" : "W"}
                  </span>
                  {i === 0 && <span className="command-bar-meta">⏎</span>}
                </>
              ) : (
                <>
                  <span className="command-bar-value-sans">{match.name}</span>
                  <span className="command-bar-meta">{match.areaKm2.toFixed(1)} km²</span>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
