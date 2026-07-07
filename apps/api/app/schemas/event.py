import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    monitor_id: uuid.UUID
    aoi_id: uuid.UUID
    analysis_result_id: uuid.UUID
    metric_value: float
    threshold: float
    summary: str
    created_at: datetime
