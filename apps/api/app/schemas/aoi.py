import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, field_validator

from app.schemas.geo import validate_aoi_geometry, wkb_to_geojson

if TYPE_CHECKING:
    from app.models.aoi import AOI


class AOIBase(BaseModel):
    name: str
    description: str | None = None


class AOICreate(AOIBase):
    geometry: dict  # GeoJSON Polygon

    @field_validator("geometry")
    @classmethod
    def _geometry_is_sane(cls, value: dict) -> dict:
        return validate_aoi_geometry(value)


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
            created_at=aoi.created_at,
            updated_at=aoi.updated_at,
            archived_at=aoi.archived_at,
        )
