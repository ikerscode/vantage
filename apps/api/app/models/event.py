import uuid

from sqlalchemy import Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class Event(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "event"

    # An event has no meaning without its monitor; cascades on monitor delete.
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("monitor.id", ondelete="CASCADE"), nullable=False, index=True
    )
    aoi_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("aoi.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    analysis_result_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("analysis_result.id", ondelete="CASCADE"),
        nullable=False,
    )
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
