"""create core tables (aoi, monitor, analysis_result, event)

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "aoi",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "geom",
            Geometry(geometry_type="POLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_aoi"),
    )
    op.create_index("idx_aoi_geom", "aoi", ["geom"], unique=False, postgresql_using="gist")

    op.create_table(
        "monitor",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aoi_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule", sa.String(length=128), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("baseline_date", sa.Date(), nullable=True),
        sa.Column("last_scene_date", sa.Date(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["aoi_id"], ["aoi.id"], name="fk_monitor_aoi_id_aoi", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_monitor"),
    )
    op.create_index("ix_monitor_aoi_id", "monitor", ["aoi_id"], unique=False)

    op.create_table(
        "analysis_result",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aoi_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monitor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("date_a", sa.Date(), nullable=False),
        sa.Column("date_b", sa.Date(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("s3_key", sa.String(length=512), nullable=True),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["aoi_id"], ["aoi.id"], name="fk_analysis_result_aoi_id_aoi", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["monitor_id"],
            ["monitor.id"],
            name="fk_analysis_result_monitor_id_monitor",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_analysis_result"),
    )
    op.create_index(
        "ix_analysis_result_aoi_id", "analysis_result", ["aoi_id"], unique=False
    )

    op.create_table(
        "event",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monitor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aoi_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["monitor_id"], ["monitor.id"], name="fk_event_monitor_id_monitor", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["aoi_id"], ["aoi.id"], name="fk_event_aoi_id_aoi", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["analysis_result_id"],
            ["analysis_result.id"],
            name="fk_event_analysis_result_id_analysis_result",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_event"),
    )
    op.create_index("ix_event_monitor_id", "event", ["monitor_id"], unique=False)
    op.create_index("ix_event_aoi_id", "event", ["aoi_id"], unique=False)


def downgrade() -> None:
    op.drop_table("event")
    op.drop_table("analysis_result")
    op.drop_table("monitor")
    op.drop_index("idx_aoi_geom", table_name="aoi", postgresql_using="gist")
    op.drop_table("aoi")
