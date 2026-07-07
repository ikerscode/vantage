import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.models.analysis_result import AnalysisResult


class AnalysisCreate(BaseModel):
    aoi_id: uuid.UUID
    date_a: date
    date_b: date
    threshold: float | None = None  # falls back to settings.change_detection_default_threshold


class AnalysisRead(BaseModel):
    id: uuid.UUID
    aoi_id: uuid.UUID
    monitor_id: uuid.UUID | None
    date_a: date
    date_b: date
    threshold: float
    status: str
    error_message: str | None
    stats: dict | None
    tilejson_url: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_model(
        cls, analysis: "AnalysisResult", *, tilejson_url: str | None = None
    ) -> "AnalysisRead":
        return cls(
            id=analysis.id,
            aoi_id=analysis.aoi_id,
            monitor_id=analysis.monitor_id,
            date_a=analysis.date_a,
            date_b=analysis.date_b,
            threshold=analysis.threshold,
            status=analysis.status,
            error_message=analysis.error_message,
            stats=analysis.stats,
            tilejson_url=tilejson_url,
            created_at=analysis.created_at,
            updated_at=analysis.updated_at,
            completed_at=analysis.completed_at,
        )
