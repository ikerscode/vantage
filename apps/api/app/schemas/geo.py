import math

from geoalchemy2 import WKBElement
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity

EARTH_RADIUS_KM = 6371
# Generous relative to a single MGRS tile (~12,100 km²) -- comfortably
# above any real single-AOI use case this tool targets, comfortably below
# "a whole country/continent got selected by mistake" (a lon/lat swap or a
# stray extra vertex in a drawn polygon are the realistic ways this
# actually happens, not a deliberate huge AOI).
MAX_AOI_AREA_KM2 = 50_000


def _area_km2(geom: BaseGeometry) -> float:
    """Same equirectangular-projection approximation as the frontend's
    polygonAreaKm2 (apps/web/src/lib/geo.ts) — accurate enough for a
    server-side sanity bound, not a substitute for a real geodesic area."""
    ring = list(geom.exterior.coords)
    if len(ring) < 3:
        return 0.0
    mean_lat_rad = math.radians(sum(lat for _lon, lat in ring) / len(ring))
    cos_lat = math.cos(mean_lat_rad)
    points = [(lon * math.pi / 180 * EARTH_RADIUS_KM * cos_lat, lat * math.pi / 180 * EARTH_RADIUS_KM) for lon, lat in ring]
    total = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return abs(total / 2)


def validate_aoi_geometry(geometry: dict) -> dict:
    """BRIEF v2, found for real: AOICreate.geometry was a completely
    unvalidated raw dict -- a malformed GeoJSON payload (missing "type", a
    non-Polygon type, an unclosed/self-intersecting ring) reached
    shape(...) with no prior check, surfacing as an unhandled 500 from deep
    inside Shapely/GeoAlchemy2 rather than a clean 422 naming the actual
    problem. Also catches a degenerate (zero-area) or implausibly huge
    polygon -- the latter is exactly what a lon/lat coordinate-order bug
    (a real, easy mistake with GeoJSON's [lon, lat] ordering) produces."""
    if geometry.get("type") != "Polygon":
        raise ValueError(f"geometry must be a GeoJSON Polygon (got type={geometry.get('type')!r})")

    try:
        geom = shape(geometry)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"invalid GeoJSON geometry: {exc}") from exc

    if not geom.is_valid:
        raise ValueError(f"polygon is not a valid (simple, non-self-intersecting) geometry: {explain_validity(geom)}")

    area = _area_km2(geom)
    if area <= 0:
        raise ValueError("polygon has zero area — check for a degenerate or unclosed ring")
    if area > MAX_AOI_AREA_KM2:
        raise ValueError(
            f"polygon area ({area:,.0f} km²) exceeds the {MAX_AOI_AREA_KM2:,} km² sanity limit — "
            "if this is intentional, split it into smaller AOIs; if not, check for a lon/lat coordinate-order mistake"
        )
    return geometry


def geojson_to_wkb(geometry: dict, srid: int = 4326) -> WKBElement:
    """GeoJSON dict (as received over the wire) -> WKBElement for a Geometry column."""
    return from_shape(shape(geometry), srid=srid)


def wkb_to_geojson(geom: WKBElement) -> dict:
    """A Geometry column's WKBElement -> plain GeoJSON dict for the wire."""
    return mapping(to_shape(geom))
