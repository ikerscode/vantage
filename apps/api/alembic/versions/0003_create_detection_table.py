"""create detection table

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "detection",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "bbox",
            Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("chip_s3_key", sa.String(length=512), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["analysis_result_id"],
            ["analysis_result.id"],
            name="fk_detection_analysis_result_id_analysis_result",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_detection"),
    )
    op.create_index(
        "ix_detection_analysis_result_id", "detection", ["analysis_result_id"], unique=False
    )
    op.create_index("idx_detection_bbox", "detection", ["bbox"], unique=False, postgresql_using="gist")


def downgrade() -> None:
    op.drop_index("idx_detection_bbox", table_name="detection", postgresql_using="gist")
    op.drop_table("detection")
