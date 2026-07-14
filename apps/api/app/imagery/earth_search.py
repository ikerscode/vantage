from datetime import date

from pystac_client import Client

from app.core.config import settings
from app.imagery.base import ImagerySource, SceneMetadata

# Earth Search v1 sentinel-2-l2a asset keys we care about (visual true-color,
# band-math inputs, and the SCL cloud mask), plus sentinel-1-grd's
# polarization bands (each its own single-band COG, like optical's red/nir --
# see app/imagery/sensor.py for how a collection routes to the pipeline that
# reads these). Harmless to list both sensors' keys in one tuple: `if key in
# item.assets` below means an optical item simply never has "vv"/"vh" and
# vice versa.
ASSET_KEYS = ("visual", "red", "green", "blue", "nir", "scl", "vv", "vh", "hh", "hv")

# BRIEF v2, found for real on a live install: search() paged through EVERY
# matching item with no cap and no network timeout. A continent-sized AOI
# (drawn zoomed-out on a basemap-less map — 32.5M km², an easy real mistake
# with nothing on screen for scale; newer installs reject it at creation
# via MAX_AOI_AREA_KM2, but this one predated that) over the frontend's
# 24-month default window matches MILLIONS of Sentinel-2 items — items()
# dutifully paged through them, hanging the API request (and the UI waiting
# on it, with no visible feedback) effectively forever. The scrubber renders
# individual scene ticks, so beyond a couple hundred scenes nothing more is
# even displayable — a hard cap loses nothing real. The timeout bounds every
# underlying HTTP call so a stalled connection can't hang a request either.
MAX_SEARCH_ITEMS = 200
REQUEST_TIMEOUT_S = 30


class EarthSearchSource(ImagerySource):
    """v1 concrete ImagerySource: Element84 Earth Search v1, public unsigned COGs."""

    def __init__(self, stac_api_url: str | None = None):
        self._client = Client.open(stac_api_url or settings.stac_api_url, timeout=REQUEST_TIMEOUT_S)

    def search(
        self,
        geometry: dict,
        date_from: date,
        date_to: date,
        collections: list[str],
        max_cloud_cover: float | None = None,
    ) -> list[SceneMetadata]:
        query = {"eo:cloud_cover": {"lt": max_cloud_cover}} if max_cloud_cover is not None else None

        search = self._client.search(
            collections=collections,
            intersects=geometry,
            datetime=f"{date_from.isoformat()}/{date_to.isoformat()}",
            query=query,
            max_items=MAX_SEARCH_ITEMS,
        )

        scenes = []
        for item in search.items():
            assets = {key: item.assets[key].href for key in ASSET_KEYS if key in item.assets}
            scenes.append(
                SceneMetadata(
                    id=item.id,
                    collection=item.collection_id,
                    datetime=item.datetime.isoformat() if item.datetime else "",
                    cloud_cover=item.properties.get("eo:cloud_cover"),
                    bbox=tuple(item.bbox) if item.bbox else (0.0, 0.0, 0.0, 0.0),
                    assets=assets,
                    self_href=item.get_self_href(),
                    orbit_state=item.properties.get("sat:orbit_state"),
                )
            )
        return scenes

    def get_asset_href(self, item_id: str, collection: str, asset_key: str) -> str:
        items = list(self._client.search(collections=[collection], ids=[item_id]).items())
        if not items:
            raise ValueError(f"item {item_id!r} not found in collection {collection!r}")
        item = items[0]
        if asset_key not in item.assets:
            raise ValueError(f"asset {asset_key!r} not found on item {item_id!r}")
        return item.assets[asset_key].href
