import type { GeoJSONPolygon } from "../api/types";

const EARTH_RADIUS_KM = 6371;

/**
 * Approximate polygon area in km² via an equirectangular projection scaled
 * by cos(mean latitude), then the shoelace formula. Accurate enough for the
 * AOI sizes this tool deals with (single-digit to low-hundreds km²) without
 * pulling in a full geodesic library for a HUD label.
 */
export function polygonAreaKm2(geometry: GeoJSONPolygon): number {
  const ring = geometry.coordinates[0];
  if (!ring || ring.length < 3) return 0;

  const meanLatRad = (ring.reduce((sum, [, lat]) => sum + lat, 0) / ring.length) * (Math.PI / 180);
  const cosLat = Math.cos(meanLatRad);

  const points = ring.map(([lon, lat]) => ({
    x: lon * (Math.PI / 180) * EARTH_RADIUS_KM * cosLat,
    y: lat * (Math.PI / 180) * EARTH_RADIUS_KM,
  }));

  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    sum += a.x * b.y - b.x * a.y;
  }
  return Math.abs(sum / 2);
}

export function polygonCentroid(geometry: GeoJSONPolygon): { longitude: number; latitude: number } {
  const ring = geometry.coordinates[0];
  const [lonSum, latSum] = ring.reduce(
    ([lonAcc, latAcc], [lon, lat]) => [lonAcc + lon, latAcc + lat],
    [0, 0],
  );
  return { longitude: lonSum / ring.length, latitude: latSum / ring.length };
}
