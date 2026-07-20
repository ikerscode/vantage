import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class AnalysisStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class DetectionStatus(str, enum.Enum):
    """Outcome of the object-detection sub-step, tracked SEPARATELY from the
    analysis's own status: detection is best-effort and its failure must not
    flip an otherwise-successful change analysis to FAILED (see
    app.tasks.change_detection). But swallowing it silently made a "0
    detections" result ambiguous — ran-and-found-nothing vs never-ran vs
    inference-unreachable all looked identical (CLAUDE.md §3, honest seams).
    This records which actually happened."""

    OK = "ok"  # detection ran to completion (detection_count may still be 0)
    FAILED = "failed"  # detection was attempted but errored (see detection_error)
    SKIPPED = "skipped"  # not attempted — e.g. a SAR AOI has no honest detector


class AnalysisResult(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "analysis_result"

    aoi_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("aoi.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Set when this analysis was produced by a monitor sweep rather than a manual request.
    monitor_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("monitor.id", ondelete="SET NULL"), nullable=True
    )
    date_a: Mapped[date] = mapped_column(Date, nullable=False)
    date_b: Mapped[date] = mapped_column(Date, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AnalysisStatus.PENDING.value
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    stats: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Object-detection sub-step outcome (see DetectionStatus). Nullable: null
    # means detection hasn't run yet (analysis still pending/running) or this
    # row predates the sub-step being tracked. detection_count is the number of
    # objects found on an OK run (0 is a real, honest answer, not a failure).
    detection_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    detection_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detection_error: Mapped[str | None] = mapped_column(Text, nullable=True)
