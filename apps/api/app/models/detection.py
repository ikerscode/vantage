import uuid

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPkMixin


class Detection(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "detection"

    analysis_result_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("analysis_result.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bbox: Mapped[WKBElement] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326, spatial_index=True), nullable=False
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    chip_s3_key: Mapped[str] = mapped_column(String(512), nullable=False)
