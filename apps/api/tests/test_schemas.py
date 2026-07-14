"""BRIEF v2: real regression coverage for input validation added to close
gaps found during a live review pass — none of these were previously
checked at all, so a bad request either reached the database/a background
Celery job unchecked, or (worse, for monitor schedules) crashed the entire
sweep for every OTHER monitor too (see app/tasks/monitor_sweep.py)."""

import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.aoi import AOICreate
from app.schemas.analysis_result import AnalysisCreate
from app.schemas.monitor import MonitorCreate

_SMALL_VALID_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[-121.5, 38.5], [-121.4, 38.5], [-121.4, 38.6], [-121.5, 38.6], [-121.5, 38.5]]],
}


class TestMonitorValidation:
    def test_valid_cron_and_threshold_accepted(self):
        m = MonitorCreate(aoi_id=uuid.uuid4(), schedule="0 6 * * *", threshold=0.3)
        assert m.schedule == "0 6 * * *"
        assert m.threshold == 0.3

    def test_invalid_cron_rejected(self):
        # This exact case used to reach app/tasks/monitor_sweep.py's
        # sweep_monitors() loop unchecked, where croniter() raised
        # unhandled and crashed the sweep for every OTHER active monitor
        # too, not just this one.
        with pytest.raises(ValidationError, match="not a valid 5-field cron"):
            MonitorCreate(aoi_id=uuid.uuid4(), schedule="not a cron")

    def test_threshold_out_of_range_rejected(self):
        with pytest.raises(ValidationError, match="threshold must be between 0 and 40"):
            MonitorCreate(aoi_id=uuid.uuid4(), schedule="0 6 * * *", threshold=200)

    def test_negative_threshold_rejected(self):
        with pytest.raises(ValidationError, match="threshold must be between 0 and 40"):
            MonitorCreate(aoi_id=uuid.uuid4(), schedule="0 6 * * *", threshold=-0.1)

    def test_sar_scale_threshold_accepted(self):
        # The bound was widened from [0, 2] (NDVI-diff only) to [0, 40] so a
        # SAR log-ratio dB threshold (see app/imagery/sensor.py's
        # default_change_threshold_for) fits the same field — this is the
        # regression guard for that widening.
        m = MonitorCreate(aoi_id=uuid.uuid4(), schedule="0 6 * * *", threshold=5.0)
        assert m.threshold == 5.0

    def test_detect_on_change_defaults_true(self):
        m = MonitorCreate(aoi_id=uuid.uuid4(), schedule="0 6 * * *")
        assert m.detect_on_change is True


class TestAnalysisValidation:
    def test_valid_distinct_dates_accepted(self):
        a = AnalysisCreate(aoi_id=uuid.uuid4(), date_a=date(2025, 1, 1), date_b=date(2025, 6, 1))
        assert a.date_a != a.date_b

    def test_identical_dates_rejected(self):
        # Previously ran a real Celery job that fetched the same scene
        # twice and diffed it against itself — always "no change", a
        # silently misleading result rather than a clear rejection.
        with pytest.raises(ValidationError, match="must be different dates"):
            AnalysisCreate(aoi_id=uuid.uuid4(), date_a=date(2025, 1, 1), date_b=date(2025, 1, 1))

    def test_threshold_out_of_range_rejected(self):
        with pytest.raises(ValidationError, match="threshold must be between 0 and 40"):
            AnalysisCreate(aoi_id=uuid.uuid4(), date_a=date(2025, 1, 1), date_b=date(2025, 6, 1), threshold=200)


class TestAoiGeometryValidation:
    def test_valid_small_polygon_accepted(self):
        aoi = AOICreate(name="test", geometry=_SMALL_VALID_POLYGON)
        assert aoi.geometry["type"] == "Polygon"

    def test_collection_defaults_to_optical(self):
        aoi = AOICreate(name="test", geometry=_SMALL_VALID_POLYGON)
        assert aoi.collection == "sentinel-2-l2a"

    def test_sar_collection_accepted(self):
        aoi = AOICreate(name="test", geometry=_SMALL_VALID_POLYGON, collection="sentinel-1-grd")
        assert aoi.collection == "sentinel-1-grd"

    def test_unknown_collection_rejected(self):
        with pytest.raises(ValidationError, match="unrecognized STAC collection"):
            AOICreate(name="test", geometry=_SMALL_VALID_POLYGON, collection="landsat-c2-l2")

    def test_non_polygon_type_rejected(self):
        with pytest.raises(ValidationError, match="must be a GeoJSON Polygon"):
            AOICreate(name="test", geometry={"type": "Point", "coordinates": [1, 2]})

    def test_self_intersecting_polygon_rejected(self):
        bowtie = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}
        with pytest.raises(ValidationError, match="not a valid.*geometry"):
            AOICreate(name="test", geometry=bowtie)

    def test_implausibly_huge_polygon_rejected(self):
        # The realistic way this happens is a lon/lat coordinate-order
        # mistake, not a deliberately huge AOI.
        huge = {
            "type": "Polygon",
            "coordinates": [[[-170, -80], [170, -80], [170, 80], [-170, 80], [-170, -80]]],
        }
        with pytest.raises(ValidationError, match="exceeds the.*sanity limit"):
            AOICreate(name="test", geometry=huge)

    def test_demo_seed_scale_polygon_stays_well_under_the_limit(self):
        # Regression guard tying the sanity cap to a real, already-shipped
        # value (BRIEF v1.3's demo AOI, "Demo — Central Valley, CA",
        # 222.9 km²) — this must never accidentally start rejecting a
        # realistic single-AOI use case.
        central_valley_scale = {
            "type": "Polygon",
            "coordinates": [[[-121.6, 38.4], [-121.4, 38.4], [-121.4, 38.55], [-121.6, 38.55], [-121.6, 38.4]]],
        }
        aoi = AOICreate(name="Demo — Central Valley, CA", geometry=central_valley_scale)
        assert aoi.geometry is not None
