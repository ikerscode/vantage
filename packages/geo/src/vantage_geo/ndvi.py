import numpy as np


def compute_ndvi(nir: np.ndarray, red: np.ndarray, *, nodata: float = np.nan) -> np.ndarray:
    """NDVI = (nir - red) / (nir + red), as float32. Cells where nir+red == 0 get `nodata`."""
    nir = nir.astype(np.float32)
    red = red.astype(np.float32)
    denom = nir + red
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = (nir - red) / denom
    return np.where(denom == 0, np.float32(nodata), ndvi).astype(np.float32)
