import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, field_validator, model_validator

if TYPE_CHECKING:
    from app.models.analysis_result import AnalysisResult


class AnalysisCreate(BaseModel):
    aoi_id: uuid.UUID
    date_a: date
    date_b: date
    threshold: float | None = None  # falls back to settings.change_detection_default_threshold

    @field_validator("threshold")
    @classmethod
    def _threshold_in_range(cls, value: float | None) -> float | None:
        # Same bound as MonitorBase's identical validator (app/schemas/
        # monitor.py) — NDVI-diff never exceeds 2.0 since NDVI itself is in
        # [-1, 1]. Found for real worth adding: nothing previously stopped
        # a request for e.g. threshold=20 (meant as a percent, not a raw
        # NDVI-diff value) from creating an analysis that could then never
        # detect any change at all, silently.
        if value is not None and not (0 <= value <= 2):
            raise ValueError(f"threshold must be between 0 and 2 (got {value})")
        return value

    @model_validator(mode="after")
    def _dates_are_distinct(self) -> "AnalysisCreate":
        # BRIEF v2, found for real: nothing stopped date_a == date_b, which
        # change_detection_pipeline.py would still run (fetching the same
        # scene for both dates, diffing an image against itself) — a real
        # Celery job and real compute spent to always report "no change",
        # which is a confusing, silently-misleading result rather than a
        # clear rejection at the one point (request time) it's actually
        # cheap and unambiguous to catch.
        if self.date_a == self.date_b:
            raise ValueError("date_a and date_b must be different dates")
        return self


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
