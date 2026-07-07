import numpy as np

from vantage_geo.diff import (
    GAIN_COLOR,
    LOSS_COLOR,
    colorize_diff,
    ndvi_diff,
    summarize_diff,
    threshold_mask,
)


def test_ndvi_diff():
    ndvi_a = np.array([[0.1, 0.5]], dtype=np.float32)
    ndvi_b = np.array([[0.3, 0.2]], dtype=np.float32)

    result = ndvi_diff(ndvi_a, ndvi_b)

    np.testing.assert_allclose(result, [[0.2, -0.3]], rtol=1e-6)


def test_threshold_mask_boundary_is_included():
    diff = np.array([0.2, -0.2, 0.19999, 0.0])

    mask = threshold_mask(diff, threshold=0.2)

    np.testing.assert_array_equal(mask, [True, True, False, False])


def test_colorize_diff_masks_invalid_pixels_regardless_of_magnitude():
    diff = np.array([[0.5, -0.5], [0.5, 0.0]], dtype=np.float32)
    # bottom-left pixel has a large diff but is invalid (cloud/shadow) -> must stay transparent
    valid_mask = np.array([[True, True], [False, True]])

    rgba = colorize_diff(diff, valid_mask, threshold=0.2)

    assert tuple(rgba[0, 0]) == GAIN_COLOR
    assert tuple(rgba[0, 1]) == LOSS_COLOR
    assert tuple(rgba[1, 0]) == (0, 0, 0, 0)
    assert tuple(rgba[1, 1]) == (0, 0, 0, 0)


def test_summarize_diff():
    diff = np.array([0.5, -0.5, 0.05], dtype=np.float32)
    valid_mask = np.array([True, True, True])
    changed_mask = threshold_mask(diff, threshold=0.2) & valid_mask

    stats = summarize_diff(diff, changed_mask, valid_mask)

    assert stats["valid_pixel_count"] == 3
    assert stats["changed_pixel_count"] == 2
    assert stats["pct_changed"] == 2 / 3
    assert stats["mean_diff"] is not None
    assert stats["max_abs_diff"] == 0.5


def test_summarize_diff_no_valid_pixels():
    diff = np.zeros((2, 2), dtype=np.float32)
    valid_mask = np.zeros((2, 2), dtype=bool)
    changed_mask = np.zeros((2, 2), dtype=bool)

    stats = summarize_diff(diff, changed_mask, valid_mask)

    assert stats["valid_pixel_count"] == 0
    assert stats["pct_changed"] == 0.0
    assert stats["mean_diff"] is None
