import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class Monitor(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "monitor"

    aoi_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("aoi.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Cron expression (parsed with croniter), e.g. "0 */6 * * *" for every 6 hours.
    schedule: Mapped[str] = mapped_column(String(128), nullable=False)
    # Falls back to settings.change_detection_default_threshold when null.
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Fixed comparison baseline; when null, sweeps use a rolling comparison against last_scene_date.
    baseline_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_scene_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
