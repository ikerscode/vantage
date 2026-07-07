import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class MonitorBase(BaseModel):
    aoi_id: uuid.UUID
    schedule: str
    threshold: float | None = None
    active: bool = True
    baseline_date: date | None = None


class MonitorCreate(MonitorBase):
    pass


class MonitorUpdate(BaseModel):
    schedule: str | None = None
    threshold: float | None = None
    active: bool | None = None
    baseline_date: date | None = None


class MonitorRead(MonitorBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    last_scene_date: date | None
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
