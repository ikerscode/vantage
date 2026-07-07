import numpy as np

from vantage_geo.scl import scl_cloud_mask


def test_scl_cloud_mask_masks_invalid_classes():
    # 0=no data, 3=shadow, 8/9=cloud med/high, 10=cirrus (masked);
    # 4/5/6=veg/bare-soil/water (kept)
    scl = np.array([0, 3, 4, 5, 6, 8, 9, 10], dtype=np.uint8)

    mask = scl_cloud_mask(scl)

    expected = np.array([True, True, False, False, False, True, True, True])
    np.testing.assert_array_equal(mask, expected)


def test_scl_cloud_mask_custom_classes():
    scl = np.array([1, 2, 3], dtype=np.uint8)

    mask = scl_cloud_mask(scl, mask_classes=frozenset({1}))

    np.testing.assert_array_equal(mask, [True, False, False])
