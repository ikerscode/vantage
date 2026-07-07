import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.schemas.geo import wkb_to_geojson

if TYPE_CHECKING:
    from app.models.detection import Detection


class DetectionRead(BaseModel):
    id: uuid.UUID
    analysis_result_id: uuid.UUID
    bbox: dict  # GeoJSON Polygon
    label: str
    score: float
    chip_s3_key: str
    created_at: datetime

    @classmethod
    def from_model(cls, detection: "Detection") -> "DetectionRead":
        return cls(
            id=detection.id,
            analysis_result_id=detection.analysis_result_id,
            bbox=wkb_to_geojson(detection.bbox),
            label=detection.label,
            score=detection.score,
            chip_s3_key=detection.chip_s3_key,
            created_at=detection.created_at,
        )
