import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, true
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
    # BRIEF v2: when a sweep finds a real change (not just "ran"), also run
    # object detection over the post-change scene so the analyst sees WHAT
    # changed, not just that something did -- see app/tasks/monitor_sweep.py.
    # Only takes effect for optical AOIs (app/imagery/sensor.py) even when
    # true; there's no honest object detector for SAR amplitude imagery yet
    # (see sar_change_detection_pipeline.py's module docstring), so this is
    # silently a no-op for a SAR monitor rather than running a COCO detector
    # against data it was never trained on. Defaults on: this is the
    # behavior an analyst setting up a monitor almost always wants, and
    # detection only ever runs on sweeps that already found a real change,
    # not every tick, so the default doesn't add unconditional GPU/CPU load.
    detect_on_change: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    # Fixed comparison baseline; when null, sweeps use a rolling comparison against last_scene_date.
    baseline_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_scene_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
