import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.schemas.geo import wkb_to_geojson

if TYPE_CHECKING:
    from app.models.aoi import AOI


class AOIBase(BaseModel):
    name: str
    description: str | None = None


class AOICreate(AOIBase):
    geometry: dict  # GeoJSON Polygon


class AOIUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    geometry: dict | None = None


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
