import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, field_validator

from app.core.config import settings
from app.imagery.sensor import sensor_for_collection
from app.schemas.geo import validate_aoi_geometry, wkb_to_geojson

if TYPE_CHECKING:
    from app.models.aoi import AOI


class AOIBase(BaseModel):
    name: str
    description: str | None = None


class AOICreate(AOIBase):
    geometry: dict  # GeoJSON Polygon
    # Sensor this AOI is tracked with -- "sentinel-2-l2a" (optical, default)
    # or "sentinel-1-grd" (SAR); see app/imagery/sensor.py. Fixed for the
    # AOI's lifetime: every Explore/Analyze/Monitor use of it goes through
    # whichever pipeline this collection dispatches to.
    collection: str = settings.stac_default_collection

    @field_validator("geometry")
    @classmethod
    def _geometry_is_sane(cls, value: dict) -> dict:
        return validate_aoi_geometry(value)

    @field_validator("collection")
    @classmethod
    def _collection_is_known(cls, value: str) -> str:
        sensor_for_collection(value)  # raises ValueError if unrecognized
        return value


class AOIUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    geometry: dict | None = None

    @field_validator("geometry")
    @classmethod
    def _geometry_is_sane(cls, value: dict | None) -> dict | None:
        return validate_aoi_geometry(value) if value is not None else None


class AOIRead(AOIBase):
    id: uuid.UUID
    geometry: dict
    collection: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None

    @classmethod
    def from_model(cls, aoi: "AOI") -> "AOIRead":
        return cls(
            id=aoi.id,
            name=aoi.name,
            description=aoi.description,
            geometry=wkb_to_geojson(aoi.geom),
            collection=aoi.collection,
            created_at=aoi.created_at,
            updated_at=aoi.updated_at,
            archived_at=aoi.archived_at,
        )
