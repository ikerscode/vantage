from datetime import datetime

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class AOI(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "aoi"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    geom: Mapped[WKBElement] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True), nullable=False
    )
    # Soft-delete marker: hard-deleting an AOI would orphan AnalysisResult/Event history.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
