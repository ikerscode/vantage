import enum

from app.core.config import settings


class SensorType(str, enum.Enum):
    OPTICAL = "optical"
    SAR = "sar"


# Every STAC collection VANTAGE knows how to search/render/change-detect,
# tagged by the physical sensor family that decides which pipeline applies
# (see app.services.change_detection_pipeline's dispatcher and
# app.services.sar_change_detection_pipeline). A new *collection* of an
# already-supported sensor family (e.g. sentinel-1-grd's IW vs EW modes, or a
# second optical constellation) is just a new entry in one of these two sets;
# a genuinely new sensor family needs its own pipeline module, not just a
# new entry here.
OPTICAL_COLLECTIONS: frozenset[str] = frozenset({"sentinel-2-l2a"})
SAR_COLLECTIONS: frozenset[str] = frozenset({"sentinel-1-grd"})


def sensor_for_collection(collection: str) -> SensorType:
    if collection in SAR_COLLECTIONS:
        return SensorType.SAR
    if collection in OPTICAL_COLLECTIONS:
        return SensorType.OPTICAL
    # Fail loud, not silently default-to-optical: an unrecognized collection
    # reaching this far is either a data-entry bug (a typo'd AOI.collection)
    # or a genuinely new collection nobody wired a pipeline for yet. Silently
    # guessing "optical" would run NDVI band math against data that may not
    # even have red/nir assets, producing a confusing failure two layers away
    # from the actual cause instead of a clear one here.
    raise ValueError(
        f"unrecognized STAC collection {collection!r} -- add it to "
        "OPTICAL_COLLECTIONS or SAR_COLLECTIONS in app.imagery.sensor"
    )


def default_collection_for(sensor: SensorType) -> str:
    return settings.sar_collection if sensor is SensorType.SAR else settings.stac_default_collection


def default_change_threshold_for(sensor: SensorType) -> float:
    """NDVI-diff (optical) and log-ratio dB (SAR) are different physical
    units sharing one AnalysisResult.threshold column (see schemas/monitor.py
    and schemas/analysis_result.py for the widened shared bound) — each
    sensor gets its own sensible default rather than one number doing
    double duty."""
    if sensor is SensorType.SAR:
        return settings.sar_change_detection_default_threshold
    return settings.change_detection_default_threshold
