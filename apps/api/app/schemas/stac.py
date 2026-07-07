import uuid
from datetime import date

from pydantic import BaseModel, model_validator


class AssetRef(BaseModel):
    href: str
    title: str | None = None


class StacSearchRequest(BaseModel):
    aoi_id: uuid.UUID | None = None
    geometry: dict | None = None
    date_from: date
    date_to: date
    collections: list[str] = ["sentinel-2-l2a"]
    max_cloud_cover: float | None = None

    @model_validator(mode="after")
    def _require_aoi_or_geometry(self) -> "StacSearchRequest":
        if not self.aoi_id and not self.geometry:
            raise ValueError("one of aoi_id or geometry is required")
        return self


class StacItemSummary(BaseModel):
    id: str
    collection: str
    datetime: str
    cloud_cover: float | None = None
    bbox: list[float]
    assets: dict[str, AssetRef]
    # Fetchable STAC item JSON URL, used by the frontend for the tiler's
    # multi-asset NDVI band math (red/nir are separate COG files).
    self_href: str | None = None
