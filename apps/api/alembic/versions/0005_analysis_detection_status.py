"""add analysis_result detection sub-step outcome (status/count/error)

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-17

Object detection is a best-effort sub-step of a change analysis: its failure
must not fail the analysis, but swallowing it silently made "0 detections"
ambiguous (ran-and-empty vs never-ran vs inference-unreachable all looked the
same). These nullable columns record which actually happened — see
app.models.analysis_result.DetectionStatus and CLAUDE.md §3 (honest seams).
Nullable with no server_default: existing rows keep detection_status = NULL,
which the API/UI read as "not tracked / hasn't run", not as a failure.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analysis_result", sa.Column("detection_status", sa.String(length=16), nullable=True)
    )
    op.add_column("analysis_result", sa.Column("detection_count", sa.Integer(), nullable=True))
    op.add_column("analysis_result", sa.Column("detection_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_result", "detection_error")
    op.drop_column("analysis_result", "detection_count")
    op.drop_column("analysis_result", "detection_status")
