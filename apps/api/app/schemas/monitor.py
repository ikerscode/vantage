import uuid
from datetime import date, datetime

from croniter import croniter
from pydantic import BaseModel, ConfigDict, field_validator

# BRIEF v2, found for real: app/tasks/monitor_sweep.py's _is_due() calls
# croniter(monitor.schedule, ...) with no exception handling at all, inside
# a loop over every active monitor — an invalid cron string on just ONE
# monitor raises unhandled and crashes sweep_monitors() for every OTHER
# monitor too (not merely fails to schedule its own), and since celery-beat
# just re-invokes the same task on the next tick, no monitor fires again
# until that one bad row is fixed or deleted. Validating here closes the
# root cause (nothing bad ever reaches the table via the API); a defensive
# per-monitor try/except in monitor_sweep.py (BRIEF v2) closes the blast
# radius for any row that predates this validation.
def _validate_cron(value: str) -> str:
    if not croniter.is_valid(value):
        raise ValueError(f"{value!r} is not a valid 5-field cron expression")
    return value


class MonitorBase(BaseModel):
    aoi_id: uuid.UUID
    schedule: str
    threshold: float | None = None
    active: bool = True
    baseline_date: date | None = None

    @field_validator("schedule")
    @classmethod
    def _schedule_is_valid_cron(cls, value: str) -> str:
        return _validate_cron(value)

    @field_validator("threshold")
    @classmethod
    def _threshold_in_range(cls, value: float | None) -> float | None:
        # NDVI-diff thresholds are meaningfully bounded (a real diff never
        # exceeds 2.0 -- NDVI itself is in [-1, 1]) -- catches an obvious
        # fat-fingered value (e.g. "20" meant as a percent) at creation
        # time with a clear message, instead of a monitor that can now
        # never trip (or always trips) for a reason that's opaque later.
        if value is not None and not (0 <= value <= 2):
            raise ValueError(f"threshold must be between 0 and 2 (got {value})")
        return value


class MonitorCreate(MonitorBase):
    pass


class MonitorUpdate(BaseModel):
    schedule: str | None = None
    threshold: float | None = None
    active: bool | None = None
    baseline_date: date | None = None

    @field_validator("schedule")
    @classmethod
    def _schedule_is_valid_cron(cls, value: str | None) -> str | None:
        return _validate_cron(value) if value is not None else None

    @field_validator("threshold")
    @classmethod
    def _threshold_in_range(cls, value: float | None) -> float | None:
        if value is not None and not (0 <= value <= 2):
            raise ValueError(f"threshold must be between 0 and 2 (got {value})")
        return value


class MonitorRead(MonitorBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    last_scene_date: date | None
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
