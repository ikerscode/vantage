"""add aoi.collection (sensor type) and monitor.detect_on_change

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "aoi",
        sa.Column(
            "collection", sa.String(length=64), nullable=False, server_default="sentinel-2-l2a"
        ),
    )
    op.add_column(
        "monitor",
        sa.Column("detect_on_change", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("monitor", "detect_on_change")
    op.drop_column("aoi", "collection")
