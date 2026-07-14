import numpy as np
from scipy.ndimage import median_filter

# threshold_mask/colorize_diff/summarize_diff (vantage_geo.diff) are already
# unit-agnostic -- they operate on a plain float diff array plus boolean
# masks, with no NDVI-specific assumption baked in, so SAR reuses them
# directly rather than duplicating the same threshold/colorize/stats logic
# for a second unit (dB instead of NDVI-diff). This module only provides the
# SAR-specific *input* to that shared math: despeckling, a dB transform, and
# the log-ratio diff itself.


def despeckle(band: np.ndarray, size: int = 5) -> np.ndarray:
    """Median-filter speckle reduction.

    SAR amplitude imagery has multiplicative speckle noise inherent to
    coherent radar imaging -- a real, single-pixel amplitude difference
    between two dates is dominated by speckle, not ground change, unless
    it's first suppressed. A median filter is a deliberately simple choice:
    it's real, effective, and cheap, but it is NOT an adaptive speckle
    filter (Lee, Frost, Gamma-MAP) -- those model the local statistics of
    speckle more precisely and would do a better job preserving edges while
    still smoothing homogeneous areas. Swapping in one of those is a
    reasonable v2 (TODO(v2): adaptive speckle filter), not a correctness bug
    in what's here now.
    """
    return median_filter(band.astype(np.float32), size=size, mode="nearest")


def to_amplitude_db(dn: np.ndarray, *, epsilon: float = 1.0) -> np.ndarray:
    """Digital-number amplitude -> a relative dB-scale value: 20*log10(DN + epsilon).

    This is NOT calibrated sigma-naught backscatter -- true radiometric
    calibration needs the scene's calibration LUT (incidence angle, noise
    floor, per-pixel calibration constant from the product's own metadata),
    which isn't fetched here. What this *is* correct for: a RELATIVE
    log-ratio change metric between two dates of the same polarization
    (see log_ratio_diff) -- differencing two uncalibrated-but-consistent dB
    representations of the same processing chain cancels out an unknown
    but shared calibration constant to a good approximation, which is
    standard practice for simple amplitude change detection (as opposed to
    absolute backscatter analysis, which does need full calibration).
    `epsilon` keeps log(0) from a no-data/fill pixel out of the picture.
    """
    return 20.0 * np.log10(dn.astype(np.float32) + epsilon)


def log_ratio_diff(dn_a: np.ndarray, dn_b: np.ndarray, *, despeckle_size: int = 5) -> np.ndarray:
    """dB(despeckle(b)) - dB(despeckle(a)): positive = backscatter increase
    (e.g. new structure, roughening), negative = decrease (e.g. smoothing,
    flooding, clearing). Same sign convention as vantage_geo.diff.ndvi_diff
    (b - a), so threshold_mask/colorize_diff's "loss below -threshold, gain
    above +threshold" semantics apply unchanged."""
    db_a = to_amplitude_db(despeckle(dn_a, size=despeckle_size))
    db_b = to_amplitude_db(despeckle(dn_b, size=despeckle_size))
    return (db_b - db_a).astype(np.float32)


def sar_nodata_mask(dn: np.ndarray) -> np.ndarray:
    """True where a SAR amplitude pixel is no-data -- a boundless windowed
    read pads out-of-swath/out-of-scene pixels with fill_value=0 (same
    convention as the optical pipeline's boundless reads), and 0 amplitude
    isn't a physically real radar return either way. There's no cloud/cirrus
    concept for SAR (radar sees through both), so this is the whole invalid
    mask -- unlike optical's scl_cloud_mask, no scene classification layer
    is involved."""
    return dn == 0
