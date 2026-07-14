"""Sentinel-1 GRD (SAR) change detection: a log-ratio dB diff on the VV
polarization, the standard simple approach for amplitude-based SAR change
detection (used e.g. in flood mapping and general anomaly monitoring) —
distinct from, but structurally parallel to, change_detection_pipeline.py's
NDVI-diff optical pipeline. Both dispatch from
change_detection_pipeline.execute_change_detection based on the AOI's
collection (see app/imagery/sensor.py).

Honest scope, stated once here rather than scattered across comments:
  - No radiometric (sigma-naught) calibration — see vantage_geo.sar's
    to_amplitude_db docstring for why a relative log-ratio doesn't need it.
  - No terrain/incidence-angle correction. Scene selection prefers matching
    orbit direction (ascending/descending) across date_a/date_b to reduce
    the resulting geometry confound (pick_best_sar_scene below), but this is
    a mitigation, not a correction — AnalysisResult.stats records whether the
    match actually happened (orbit_state_matched) so an analyst can see the
    caveat rather than have it silently absorbed into the result.
  - Despeckling is a plain median filter (vantage_geo.sar.despeckle), not an
    adaptive filter (Lee/Frost/Gamma-MAP) — TODO(v2).
  - No object detection over SAR chips — see detection_pipeline.py's
    run_placeholder_detection docstring for why that's a deliberate gap, not
    an oversight.
"""

from datetime import date, datetime, timezone

import numpy as np
import rasterio
from affine import Affine
from rasterio.warp import transform_bounds
from shapely.geometry import box, shape
from sqlalchemy.orm import Session

from app.imagery.base import ImagerySource, SceneMetadata
from app.imagery.factory import get_imagery_source
from app.models.aoi import AOI
from app.models.analysis_result import AnalysisResult, AnalysisStatus
from app.schemas.geo import wkb_to_geojson
from app.services.change_detection_pipeline import (
    ChangeDetectionError,
    align_to_reference,
)
from app.services.cog_writer import write_cog_bytes
from app.services.storage import put_object
from vantage_geo.diff import colorize_diff, summarize_diff, threshold_mask
from vantage_geo.sar import log_ratio_diff, sar_nodata_mask
from vantage_geo.transform import bounds_to_window


def pick_best_sar_scene(
    imagery: ImagerySource,
    geometry: dict,
    target_date: date,
    collection: str,
    preferred_orbit_state: str | None = None,
) -> SceneMetadata:
    """SAR analogue of change_detection_pipeline.pick_best_scene. SAR has no
    cloud_cover to rank candidates by (radar isn't blocked by cloud), so
    "best" means: covers the AOI, and — when a preferred orbit direction is
    given — matches it. Falls back to any covering scene if no same-orbit
    match exists on this date rather than failing outright; the caller
    records whether the match actually happened."""
    scenes = imagery.search(
        geometry=geometry, date_from=target_date, date_to=target_date, collections=[collection]
    )
    aoi_shape = shape(geometry)
    covering = [s for s in scenes if box(*s.bbox).covers(aoi_shape)]
    if not covering:
        raise ChangeDetectionError(
            f"no {collection} scene on {target_date.isoformat()} fully covers the AOI "
            f"({len(scenes)} candidate scene(s) found, none covering)"
        )
    if preferred_orbit_state is not None:
        same_orbit = [s for s in covering if s.orbit_state == preferred_orbit_state]
        if same_orbit:
            return same_orbit[0]
    return covering[0]


def _read_vv(scene: SceneMetadata, aoi_geometry_4326: dict) -> tuple[np.ndarray, Affine, object]:
    """Windowed read of the VV polarization band. VV (co-pol) is the standard
    single channel for simple amplitude change detection; cross-pol VH is
    noisier and isn't used here (TODO(v2): a dual-pol VV+VH composite)."""
    if "vv" not in scene.assets:
        raise ChangeDetectionError(f"scene {scene.id} is missing required asset 'vv'")
    with rasterio.open(scene.assets["vv"]) as src:
        bounds_in_crs = transform_bounds("EPSG:4326", src.crs, *shape(aoi_geometry_4326).bounds)
        window = bounds_to_window(src.transform, bounds_in_crs)
        vv = src.read(1, window=window, boundless=True, fill_value=0)
        window_transform = src.window_transform(window)
        crs = src.crs
    return vv, window_transform, crs


def execute_sar_change_detection(session: Session, analysis: AnalysisResult, aoi: AOI) -> None:
    """The SAR pipeline body — called from change_detection_pipeline's
    execute_change_detection dispatcher, which has already resolved `aoi`."""
    geometry = wkb_to_geojson(aoi.geom)
    imagery = get_imagery_source()
    collection = aoi.collection

    analysis.status = AnalysisStatus.RUNNING.value
    session.commit()

    scene_a = pick_best_sar_scene(imagery, geometry, analysis.date_a, collection)
    scene_b = pick_best_sar_scene(
        imagery, geometry, analysis.date_b, collection, preferred_orbit_state=scene_a.orbit_state
    )

    vv_a, transform_a, crs_a = _read_vv(scene_a, geometry)
    vv_b, transform_b, crs_b = _read_vv(scene_b, geometry)
    vv_b = align_to_reference(vv_b, transform_b, crs_b, transform_a, crs_a, vv_a.shape)

    valid_mask = ~(sar_nodata_mask(vv_a) | sar_nodata_mask(vv_b))
    diff = log_ratio_diff(vv_a, vv_b)
    changed_mask = threshold_mask(diff, analysis.threshold) & valid_mask
    rgba = colorize_diff(diff, valid_mask, analysis.threshold)
    stats = summarize_diff(diff, changed_mask, valid_mask)
    # Honest caveat, not silently absorbed (CLAUDE.md §3): whether the two
    # dates actually shared a viewing geometry, which plain amplitude change
    # detection has no way to correct for if they didn't (see module
    # docstring). None (not False) when either scene has no orbit_state at
    # all, so "unknown" stays distinguishable from "known mismatch".
    stats["orbit_state_matched"] = (
        None
        if scene_a.orbit_state is None or scene_b.orbit_state is None
        else scene_a.orbit_state == scene_b.orbit_state
    )

    cog_bytes = write_cog_bytes(rgba, transform_a, str(crs_a))
    s3_key = f"analyses/{analysis.id}.tif"
    put_object(s3_key, cog_bytes)

    analysis.status = AnalysisStatus.DONE.value
    analysis.s3_key = s3_key
    analysis.stats = stats
    analysis.completed_at = datetime.now(timezone.utc)
    session.commit()
