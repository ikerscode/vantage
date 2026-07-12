// Military Grid Reference System (MGRS) — the coordinate standard NATO and
// allied forces actually work in, rather than decimal lat/lon. This is a pure
// readout/conversion (WGS84 → UTM → MGRS): observation only, nothing that
// crosses the analysis-only boundary in CLAUDE.md §1.
//
// Standard NGA algorithm. Polar regions (|lat| > 84°N / 80°S, i.e. UPS) are
// out of scope — the app's own MIN_ZOOM/AOI limits keep operations well inside
// the UTM band, and we return null rather than emit a wrong grid there.

// WGS84 ellipsoid + UTM constants.
const A = 6378137.0;
const F = 1 / 298.257223563;
const K0 = 0.9996;
const E2 = F * (2 - F);
const E2P = E2 / (1 - E2); // e'^2

const LAT_BANDS = "CDEFGHJKLMNPQRSTUVWX"; // 8° bands from 80°S; X spans 72–84°N
const ROW_ODD = "ABCDEFGHJKLMNPQRSTUV";
const ROW_EVEN = "FGHJKLMNPQRSTUVABCDE";

function utmZone(lat: number, lon: number): number {
  let zone = Math.floor((lon + 180) / 6) + 1;
  // Norway (V/32) and Svalbard (X/31,33,35,37) zone exceptions.
  if (lat >= 56 && lat < 64 && lon >= 3 && lon < 12) zone = 32;
  if (lat >= 72 && lat < 84) {
    if (lon >= 0 && lon < 9) zone = 31;
    else if (lon >= 9 && lon < 21) zone = 33;
    else if (lon >= 21 && lon < 33) zone = 35;
    else if (lon >= 33 && lon < 42) zone = 37;
  }
  return zone;
}

function latBand(lat: number): string {
  const idx = Math.min(Math.floor((lat + 80) / 8), LAT_BANDS.length - 1);
  return LAT_BANDS[idx];
}

/**
 * Format a WGS84 lat/lon as an MGRS grid reference string, e.g.
 * "18S UJ 23414 06456". `digits` is the per-axis precision: 5 = 1 m, 4 = 10 m,
 * 3 = 100 m, … Returns null outside the UTM latitude band (polar/UPS).
 */
export function latLonToMGRS(lat: number, lon: number, digits = 5): string | null {
  if (lat < -80 || lat > 84 || !Number.isFinite(lat) || !Number.isFinite(lon)) return null;

  const zone = utmZone(lat, lon);
  const band = latBand(lat);
  const latRad = (lat * Math.PI) / 180;
  const lonRad = (lon * Math.PI) / 180;
  const lonOrigin = (((zone - 1) * 6 - 180 + 3) * Math.PI) / 180; // central meridian

  const sinLat = Math.sin(latRad);
  const cosLat = Math.cos(latRad);
  const tanLat = Math.tan(latRad);

  const N = A / Math.sqrt(1 - E2 * sinLat * sinLat);
  const T = tanLat * tanLat;
  const C = E2P * cosLat * cosLat;
  const Ad = cosLat * (lonRad - lonOrigin);

  const M =
    A *
    ((1 - E2 / 4 - (3 * E2 * E2) / 64 - (5 * E2 * E2 * E2) / 256) * latRad -
      ((3 * E2) / 8 + (3 * E2 * E2) / 32 + (45 * E2 * E2 * E2) / 1024) * Math.sin(2 * latRad) +
      ((15 * E2 * E2) / 256 + (45 * E2 * E2 * E2) / 1024) * Math.sin(4 * latRad) -
      ((35 * E2 * E2 * E2) / 3072) * Math.sin(6 * latRad));

  const easting =
    K0 *
      N *
      (Ad +
        ((1 - T + C) * Ad * Ad * Ad) / 6 +
        ((5 - 18 * T + T * T + 72 * C - 58 * E2P) * Ad * Ad * Ad * Ad * Ad) / 120) +
    500000.0;

  let northing =
    K0 *
    (M +
      N *
        tanLat *
        ((Ad * Ad) / 2 +
          ((5 - T + 9 * C + 4 * C * C) * Ad * Ad * Ad * Ad) / 24 +
          ((61 - 58 * T + T * T + 600 * C - 330 * E2P) * Ad * Ad * Ad * Ad * Ad * Ad) / 720));
  if (lat < 0) northing += 10000000.0;

  // 100 km grid square letters.
  const colLetters = ["ABCDEFGH", "JKLMNPQR", "STUVWXYZ"][(zone - 1) % 3];
  const colLetter = colLetters[Math.floor(easting / 100000) - 1];
  const rowLetters = zone % 2 === 1 ? ROW_ODD : ROW_EVEN;
  const rowLetter = rowLetters[Math.floor(northing / 100000) % 20];
  if (!colLetter || !rowLetter) return null;

  // Truncate (not round) the within-square easting/northing to `digits`.
  const scale = Math.pow(10, 5 - digits);
  const e = Math.floor((easting % 100000) / scale)
    .toString()
    .padStart(digits, "0");
  const n = Math.floor((northing % 100000) / scale)
    .toString()
    .padStart(digits, "0");

  return `${zone}${band} ${colLetter}${rowLetter} ${e} ${n}`;
}

// Minimum UTM northing (m) for each latitude band's southern edge — the
// standard NGA table used to resolve which 2,000,000 m northing multiple a
// row letter refers to. Keyed by band letter.
const MIN_NORTHING: Record<string, number> = {
  C: 1100000, D: 2000000, E: 2800000, F: 3700000, G: 4600000, H: 5500000,
  J: 6400000, K: 7300000, L: 8200000, M: 9100000, N: 0, P: 800000,
  Q: 1700000, R: 2600000, S: 3500000, T: 4400000, U: 5300000, V: 6200000,
  W: 7000000, X: 7900000,
};

/**
 * Parse an MGRS grid reference back to WGS84 lat/lon (centre of the referenced
 * square). Tolerant of spacing/case: "18S UJ 2340 0645", "18suj23400645", etc.
 * Returns null if the string isn't a well-formed MGRS reference.
 */
export function mgrsToLatLon(input: string): { lat: number; lon: number } | null {
  const s = input.toUpperCase().replace(/\s+/g, "");
  const m = /^(\d{1,2})([C-HJ-NP-X])([A-HJ-NP-Z])([A-HJ-NP-V])(\d*)$/.exec(s);
  if (!m) return null;
  const zone = Number(m[1]);
  if (zone < 1 || zone > 60) return null;
  const band = m[2];
  const colLetter = m[3];
  const rowLetter = m[4];
  const digits = m[5];
  if (digits.length % 2 !== 0 || digits.length > 10) return null;

  const half = digits.length / 2;
  const scale = Math.pow(10, 5 - half);
  const eDigits = half ? Number(digits.slice(0, half)) * scale : 0;
  const nDigits = half ? Number(digits.slice(half)) * scale : 0;

  const colLetters = ["ABCDEFGH", "JKLMNPQR", "STUVWXYZ"][(zone - 1) % 3];
  const colIdx = colLetters.indexOf(colLetter);
  if (colIdx === -1) return null;
  const easting = (colIdx + 1) * 100000 + eDigits;

  const rowLetters = zone % 2 === 1 ? ROW_ODD : ROW_EVEN;
  const rowIdx = rowLetters.indexOf(rowLetter);
  if (rowIdx === -1) return null;
  const minN = MIN_NORTHING[band];
  if (minN === undefined) return null;
  let northing = rowIdx * 100000 + nDigits;
  while (northing < minN) northing += 2000000;

  // Centre the reference within its precision cell so a coarse grid lands in
  // the middle of the square, not its SW corner.
  const cell = scale;
  return utmToLatLon(zone, band, easting + cell / 2, northing + cell / 2);
}

function utmToLatLon(zone: number, band: string, easting: number, northing: number) {
  const x = easting - 500000;
  const southern = LAT_BANDS.indexOf(band) < LAT_BANDS.indexOf("N");
  const y = southern ? northing - 10000000 : northing;

  const M = y / K0;
  const mu = M / (A * (1 - E2 / 4 - (3 * E2 * E2) / 64 - (5 * E2 * E2 * E2) / 256));
  const e1 = (1 - Math.sqrt(1 - E2)) / (1 + Math.sqrt(1 - E2));

  const phi1 =
    mu +
    ((3 * e1) / 2 - (27 * e1 * e1 * e1) / 32) * Math.sin(2 * mu) +
    ((21 * e1 * e1) / 16 - (55 * e1 * e1 * e1 * e1) / 32) * Math.sin(4 * mu) +
    ((151 * e1 * e1 * e1) / 96) * Math.sin(6 * mu) +
    ((1097 * e1 * e1 * e1 * e1) / 512) * Math.sin(8 * mu);

  const sinP = Math.sin(phi1);
  const cosP = Math.cos(phi1);
  const tanP = Math.tan(phi1);
  const N1 = A / Math.sqrt(1 - E2 * sinP * sinP);
  const T1 = tanP * tanP;
  const C1 = E2P * cosP * cosP;
  const R1 = (A * (1 - E2)) / Math.pow(1 - E2 * sinP * sinP, 1.5);
  const D = x / (N1 * K0);

  const lat =
    phi1 -
    ((N1 * tanP) / R1) *
      ((D * D) / 2 -
        ((5 + 3 * T1 + 10 * C1 - 4 * C1 * C1 - 9 * E2P) * D * D * D * D) / 24 +
        ((61 + 90 * T1 + 298 * C1 + 45 * T1 * T1 - 252 * E2P - 3 * C1 * C1) *
          D * D * D * D * D * D) /
          720);
  const lonOrigin = (zone - 1) * 6 - 180 + 3;
  const lon =
    lonOrigin +
    ((D -
      ((1 + 2 * T1 + C1) * D * D * D) / 6 +
      ((5 - 2 * C1 + 28 * T1 - 3 * C1 * C1 + 8 * E2P + 24 * T1 * T1) * D * D * D * D * D) / 120) /
      cosP) *
      (180 / Math.PI);

  return { lat: (lat * 180) / Math.PI, lon };
}
