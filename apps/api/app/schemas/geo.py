from geoalchemy2 import WKBElement
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import mapping, shape


def geojson_to_wkb(geometry: dict, srid: int = 4326) -> WKBElement:
    """GeoJSON dict (as received over the wire) -> WKBElement for a Geometry column."""
    return from_shape(shape(geometry), srid=srid)


def wkb_to_geojson(geom: WKBElement) -> dict:
    """A Geometry column's WKBElement -> plain GeoJSON dict for the wire."""
    return mapping(to_shape(geom))
