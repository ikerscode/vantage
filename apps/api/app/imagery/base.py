from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass
class SceneMetadata:
    id: str
    collection: str
    datetime: str
    cloud_cover: float | None
    bbox: tuple[float, float, float, float]
    assets: dict[str, str]  # asset_key -> href, e.g. "red" -> "https://.../B04.tif"
    # Fetchable STAC item JSON URL — used by the frontend/tiler for multi-asset
    # band math (NDVI needs red+nir, which are separate COG files; see
    # services/tiler's STACReader-based /stac router). None for sources that
    # don't expose a live item URL. StaticCatalogSource provides a real
    # file:// one (apps/api/app/imagery/static_catalog.py).
    self_href: str | None = None


class ImagerySource(ABC):
    """Provider-adapter seam: all imagery access goes through this interface
    (CLAUDE.md invariant). EarthSearchSource is the only concrete v1
    implementation; PgstacSource (a local/air-gapped catalog) is TODO(v2)."""

    @abstractmethod
    def search(
        self,
        geometry: dict,
        date_from: date,
        date_to: date,
        collections: list[str],
        max_cloud_cover: float | None = None,
    ) -> list[SceneMetadata]: ...

    @abstractmethod
    def get_asset_href(self, item_id: str, collection: str, asset_key: str) -> str: ...
