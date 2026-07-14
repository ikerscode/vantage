"""Real regression coverage for app.imagery.sensor -- the collection -> pipeline
dispatch that change_detection_pipeline.py, detection_pipeline.py, and
monitor_sweep.py all key off of. A wrong answer here would silently run the
wrong physics (NDVI band math against SAR data, or vice versa) two layers
away from where the mistake actually is."""

import pytest

from app.core.config import settings
from app.imagery.sensor import (
    SensorType,
    default_change_threshold_for,
    default_collection_for,
    sensor_for_collection,
)


def test_sentinel2_is_optical():
    assert sensor_for_collection("sentinel-2-l2a") is SensorType.OPTICAL


def test_sentinel1_is_sar():
    assert sensor_for_collection("sentinel-1-grd") is SensorType.SAR


def test_unrecognized_collection_raises():
    with pytest.raises(ValueError, match="unrecognized STAC collection"):
        sensor_for_collection("landsat-c2-l2")


def test_default_collection_for_optical_matches_settings():
    assert default_collection_for(SensorType.OPTICAL) == settings.stac_default_collection


def test_default_collection_for_sar_matches_settings():
    assert default_collection_for(SensorType.SAR) == settings.sar_collection


def test_default_change_threshold_differs_by_sensor():
    # These must NOT collapse to the same number -- NDVI-diff and SAR
    # log-ratio dB are different units (see schemas/monitor.py's widened
    # bound comment); a shared default would silently be wrong for one of them.
    optical = default_change_threshold_for(SensorType.OPTICAL)
    sar = default_change_threshold_for(SensorType.SAR)
    assert optical == settings.change_detection_default_threshold
    assert sar == settings.sar_change_detection_default_threshold
    assert optical != sar
