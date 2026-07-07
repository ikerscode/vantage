import numpy as np

# RGBA colors used to colorize the change map: vegetation loss (red), vegetation gain (green).
LOSS_COLOR = (220, 50, 47, 255)
GAIN_COLOR = (38, 166, 91, 255)
TRANSPARENT = (0, 0, 0, 0)


def ndvi_diff(ndvi_a: np.ndarray, ndvi_b: np.ndarray) -> np.ndarray:
    """NDVI(b) - NDVI(a): positive = greener/gain, negative = loss."""
    return (ndvi_b.astype(np.float32) - ndvi_a.astype(np.float32)).astype(np.float32)


def threshold_mask(diff: np.ndarray, threshold: float = 0.2) -> np.ndarray:
    """Boolean mask of pixels whose absolute NDVI change meets or exceeds `threshold`."""
    return np.abs(diff) >= threshold


def colorize_diff(
    diff: np.ndarray, valid_mask: np.ndarray, threshold: float = 0.2
) -> np.ndarray:
    """(H, W, 4) uint8 RGBA: red where NDVI dropped past threshold, green where it rose,
    transparent everywhere else (including any pixel invalid per `valid_mask`)."""
    changed = threshold_mask(diff, threshold) & valid_mask
    out = np.zeros((*diff.shape, 4), dtype=np.uint8)
    out[changed & (diff <= -threshold)] = LOSS_COLOR
    out[changed & (diff >= threshold)] = GAIN_COLOR
    return out


def _nan_safe_float(value: float) -> float | None:
    """NaN cannot round-trip through strict JSON/JSONB (Postgres rejects the
    literal token), so any NaN reduction result becomes a JSON null instead.
    `valid_mask` is meant to already exclude nodata pixels (see
    vantage_geo.scl.INVALID_SCL_CLASSES), but this is cheap insurance against
    any other real-world source of a stray NaN reaching the database."""
    return None if np.isnan(value) else value


def summarize_diff(diff: np.ndarray, changed_mask: np.ndarray, valid_mask: np.ndarray) -> dict:
    """Summary stats for an AnalysisResult row. `changed_mask` should already be AND-ed with
    `valid_mask` by the caller (e.g. `threshold_mask(diff, threshold) & valid_mask`)."""
    valid_count = int(np.count_nonzero(valid_mask))
    changed_count = int(np.count_nonzero(changed_mask))
    valid_diff = diff[valid_mask]
    mean_diff = _nan_safe_float(float(np.nanmean(valid_diff))) if valid_count else None
    max_abs_diff = _nan_safe_float(float(np.nanmax(np.abs(valid_diff)))) if valid_count else None
    return {
        "valid_pixel_count": valid_count,
        "changed_pixel_count": changed_count,
        "pct_changed": (changed_count / valid_count) if valid_count else 0.0,
        "mean_diff": mean_diff,
        "max_abs_diff": max_abs_diff,
    }
