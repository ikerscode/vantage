const NICE_METERS = [
  1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000, 500000,
  1000000, 2000000, 5000000,
];

/** Standard Web Mercator meters-per-pixel at a given zoom/latitude. */
function metersPerPixel(latitude: number, zoom: number): number {
  return (156543.03392 * Math.cos((latitude * Math.PI) / 180)) / 2 ** zoom;
}

/** Label for a scale bar of `barWidthPx` at the given lat/zoom, snapped to a "nice" round distance. */
export function scaleBarLabel(latitude: number, zoom: number, barWidthPx = 46): string {
  const metersAtFullWidth = metersPerPixel(latitude, zoom) * barWidthPx;
  const nice = NICE_METERS.reduce((best, candidate) =>
    Math.abs(candidate - metersAtFullWidth) < Math.abs(best - metersAtFullWidth) ? candidate : best,
  );
  return nice >= 1000 ? `${(nice / 1000).toFixed(nice % 1000 === 0 ? 0 : 1)} km` : `${nice} m`;
}
