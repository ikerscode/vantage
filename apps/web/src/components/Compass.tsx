import { useMapStore } from "../store/mapStore";

// A north/bearing rosette — a real map instrument, not decoration. The rose
// counter-rotates with the map bearing so the "N" always points at true north,
// giving the operator constant orientation (essential the moment the map is
// rotated off north-up). Clicking snaps back to north-up. Rendered as an SVG
// (crisp at any DPI, no path-data bloat), neutral chrome only — no accent on
// map-space, no reticle/lock-on iconography (CLAUDE.md §5).
export function Compass() {
  const bearing = useMapStore((s) => s.viewState.bearing);
  const requestNorthUp = useMapStore((s) => s.requestNorthUp);

  // Only fully asserts itself when the map is actually rotated; near north-up
  // it recedes so it's never noise.
  const offNorth = Math.abs(((bearing % 360) + 360) % 360 - 0) > 0.5 && Math.abs(bearing) > 0.5;

  return (
    <button
      type="button"
      className={offNorth ? "compass compass-active" : "compass"}
      onClick={requestNorthUp}
      title={`Heading ${Math.round(((bearing % 360) + 360) % 360)}° — click to reset north-up`}
      aria-label="Reset map to north-up"
    >
      <svg width="44" height="44" viewBox="0 0 44 44" aria-hidden="true">
        <circle cx="22" cy="22" r="20" className="compass-ring" />
        {/* Cardinal + intercardinal ticks, counter-rotated with the map so they
            stay geographically fixed. */}
        <g transform={`rotate(${-bearing} 22 22)`}>
          {[0, 45, 90, 135, 180, 225, 270, 315].map((deg) => (
            <line
              key={deg}
              x1="22"
              y1={deg % 90 === 0 ? 4 : 6}
              x2="22"
              y2={deg % 90 === 0 ? 9 : 8}
              className="compass-tick"
              transform={`rotate(${deg} 22 22)`}
            />
          ))}
          {/* North needle: a filled triangle, the one emphasized element. */}
          <path d="M22 6 L18.6 23 L22 20 L25.4 23 Z" className="compass-needle-n" />
          <path d="M22 38 L18.6 21 L22 24 L25.4 21 Z" className="compass-needle-s" />
          <text x="22" y="15.5" className="compass-n" textAnchor="middle">
            N
          </text>
        </g>
      </svg>
    </button>
  );
}
