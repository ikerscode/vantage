import numpy as np

from vantage_geo.diff import GAIN_COLOR, LOSS_COLOR, colorize_diff, summarize_diff, threshold_mask
from vantage_geo.sar import despeckle, log_ratio_diff, sar_nodata_mask, to_amplitude_db


def test_despeckle_removes_a_single_pixel_spike():
    band = np.full((7, 7), 100.0, dtype=np.float32)
    band[3, 3] = 5000.0  # one wildly out-of-place bright pixel (speckle)

    smoothed = despeckle(band, size=5)

    # The median of a 5x5 neighborhood dominated by 100s ignores the one spike.
    assert smoothed[3, 3] == 100.0


def test_despeckle_preserves_a_uniform_region():
    band = np.full((5, 5), 250.0, dtype=np.float32)

    smoothed = despeckle(band, size=3)

    np.testing.assert_allclose(smoothed, band)


def test_to_amplitude_db_is_monotonic_increasing():
    dn = np.array([0.0, 1.0, 10.0, 100.0, 1000.0], dtype=np.float32)

    db = to_amplitude_db(dn)

    assert np.all(np.diff(db) > 0)


def test_to_amplitude_db_handles_zero_without_producing_nan_or_inf():
    dn = np.array([0.0], dtype=np.float32)

    db = to_amplitude_db(dn)

    assert np.isfinite(db).all()


def test_log_ratio_diff_is_zero_for_identical_scenes():
    dn = np.full((6, 6), 500.0, dtype=np.float32)

    diff = log_ratio_diff(dn, dn, despeckle_size=3)

    np.testing.assert_allclose(diff, np.zeros((6, 6)), atol=1e-4)


def test_log_ratio_diff_is_positive_for_a_backscatter_increase():
    dn_a = np.full((6, 6), 200.0, dtype=np.float32)
    dn_b = np.full((6, 6), 2000.0, dtype=np.float32)  # much brighter return later

    diff = log_ratio_diff(dn_a, dn_b, despeckle_size=3)

    assert np.all(diff > 0)


def test_log_ratio_diff_is_negative_for_a_backscatter_decrease():
    dn_a = np.full((6, 6), 2000.0, dtype=np.float32)
    dn_b = np.full((6, 6), 200.0, dtype=np.float32)  # smoother return later (e.g. flooding)

    diff = log_ratio_diff(dn_a, dn_b, despeckle_size=3)

    assert np.all(diff < 0)


def test_sar_nodata_mask_flags_only_zero_pixels():
    dn = np.array([0.0, 1.0, 0.0, 500.0], dtype=np.float32)

    mask = sar_nodata_mask(dn)

    np.testing.assert_array_equal(mask, [True, False, True, False])


def test_sar_diff_reuses_diff_pys_shared_threshold_colorize_and_summary_math():
    # This is the real point of vantage_geo.sar's design: threshold_mask,
    # colorize_diff, and summarize_diff (vantage_geo.diff) are unit-agnostic
    # and take a SAR log-ratio dB diff exactly like an NDVI diff -- no SAR
    # special-casing needed in that shared code at all.
    dn_a = np.full((4, 4), 500.0, dtype=np.float32)
    dn_b = np.full((4, 4), 500.0, dtype=np.float32)
    dn_b[0, 0] = 5000.0  # strong local increase
    dn_b[0, 1] = 50.0  # strong local decrease

    diff = log_ratio_diff(dn_a, dn_b, despeckle_size=1)
    valid_mask = ~(sar_nodata_mask(dn_a) | sar_nodata_mask(dn_b))
    changed_mask = threshold_mask(diff, threshold=3.0) & valid_mask
    rgba = colorize_diff(diff, valid_mask, threshold=3.0)
    stats = summarize_diff(diff, changed_mask, valid_mask)

    assert tuple(rgba[0, 0]) == GAIN_COLOR
    assert tuple(rgba[0, 1]) == LOSS_COLOR
    assert stats["valid_pixel_count"] == 16
    assert stats["changed_pixel_count"] == 2
