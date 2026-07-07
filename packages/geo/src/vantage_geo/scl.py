import numpy as np

# Sentinel-2 Scene Classification Layer codes treated as invalid for change
# detection: 0=no data, 3=shadow, 8=cloud medium probability, 9=cloud high
# probability, 10=thin cirrus. 0 matters in practice, not just in theory: a
# boundless windowed read pads out-of-scene-bounds pixels with fill_value=0,
# and GDAL leaves genuine sensor no-data as SCL=0 too — both read as red=nir=0,
# which compute_ndvi correctly reports as nodata (NaN). Excluding them here is
# what keeps that NaN out of valid_mask before it ever reaches summarize_diff.
INVALID_SCL_CLASSES: frozenset[int] = frozenset({0, 3, 8, 9, 10})


def scl_cloud_mask(
    scl: np.ndarray, mask_classes: frozenset[int] = INVALID_SCL_CLASSES
) -> np.ndarray:
    """Boolean mask over an SCL array; True where the pixel is no-data,
    cloud, shadow, or cirrus (invalid for change-detection purposes)."""
    return np.isin(scl, np.array(sorted(mask_classes), dtype=scl.dtype))
