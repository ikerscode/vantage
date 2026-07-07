from datetime import date, datetime, timezone

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform_bounds
from shapely.geometry import box, shape
from sqlalchemy.orm import Session

from app.core.config import settings
from app.imagery.base import ImagerySource, SceneMetadata
from app.imagery.factory import get_imagery_source
from app.models.aoi import AOI
from app.models.analysis_result import AnalysisResult, AnalysisStatus
from app.schemas.geo import wkb_to_geojson
from app.services.cog_writer import write_cog_bytes
from app.services.storage import put_object
from vantage_geo.diff import colorize_diff, ndvi_diff, summarize_diff, threshold_mask
from vantage_geo.ndvi import compute_ndvi
from vantage_geo.scl import scl_cloud_mask
from vantage_geo.transform import bounds_to_window


class ChangeDetectionError(RuntimeError):
    """Expected pipeline failure (no covering scene, missing asset, ...) — the
    Celery task wrapper records this as AnalysisResult.error_message rather
    than letting an opaque traceback surface as the failure reason."""


def pick_best_scene(
    imagery: ImagerySource, geometry: dict, target_date: date, collection: str
) -> SceneMetadata:
    """Lowest-cloud-cover scene on `target_date` that fully covers the AOI.

    v1 scope: a single scene must cover the whole AOI; if the AOI straddles
    more than one Sentinel-2 tile, this fails clearly rather than mosaicking.
    TODO(v2): multi-scene AOI mosaicking.
    """
    scenes = imagery.search(
        geometry=geometry,
        date_from=target_date,
        date_to=target_date,
        collections=[collection],
    )
    aoi_shape = shape(geometry)
    covering = [s for s in scenes if box(*s.bbox).covers(aoi_shape)]
    if not covering:
        raise ChangeDetectionError(
            f"no {collection} scene on {target_date.isoformat()} fully covers the AOI "
            f"({len(scenes)} candidate scene(s) found, none covering)"
        )
    return min(covering, key=lambda s: s.cloud_cover if s.cloud_cover is not None else 100.0)


def _read_bands(
    scene: SceneMetadata, aoi_geometry_4326: dict
) -> tuple[np.ndarray, np.ndarray, np.ndarray, Affine, object]:
    """Windowed read of red/nir at native (10m) resolution plus SCL resampled
    to that same grid (SCL is native 20m — must be decimated to line up)."""
    for required in ("red", "nir", "scl"):
        if required not in scene.assets:
            raise ChangeDetectionError(f"scene {scene.id} is missing required asset {required!r}")

    with (
        rasterio.open(scene.assets["red"]) as red_src,
        rasterio.open(scene.assets["nir"]) as nir_src,
    ):
        bounds_in_crs = transform_bounds("EPSG:4326", red_src.crs, *shape(aoi_geometry_4326).bounds)
        window = bounds_to_window(red_src.transform, bounds_in_crs)
        red = red_src.read(1, window=window, boundless=True, fill_value=0)
        nir = nir_src.read(1, window=window, boundless=True, fill_value=0)
        window_transform = red_src.window_transform(window)
        crs = red_src.crs

    with rasterio.open(scene.assets["scl"]) as scl_src:
        scl_bounds = transform_bounds("EPSG:4326", scl_src.crs, *shape(aoi_geometry_4326).bounds)
        scl_window = bounds_to_window(scl_src.transform, scl_bounds)
        scl = scl_src.read(
            1,
            window=scl_window,
            out_shape=red.shape,
            resampling=Resampling.nearest,
            boundless=True,
            fill_value=0,
        )

    return red, nir, scl, window_transform, crs


def _align_to_reference(
    array: np.ndarray,
    src_transform: Affine,
    src_crs: object,
    ref_transform: Affine,
    ref_crs: object,
    ref_shape: tuple[int, int],
) -> np.ndarray:
    """Reproject onto the reference grid if CRS/transform/shape differ (date B
    landed on a different MGRS tile than date A)."""
    if src_crs == ref_crs and src_transform == ref_transform and array.shape == ref_shape:
        return array
    aligned = np.zeros(ref_shape, dtype=array.dtype)
    reproject(
        source=array,
        destination=aligned,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=ref_transform,
        dst_crs=ref_crs,
        resampling=Resampling.nearest,
    )
    return aligned


def execute_change_detection(session: Session, analysis: AnalysisResult) -> None:
    """The real change-detection pipeline logic — takes a plain Session so
    it's unit-testable without Celery. The Celery task in
    app.tasks.change_detection is a thin wrapper around this."""
    aoi = session.get(AOI, analysis.aoi_id)
    if aoi is None:
        raise ChangeDetectionError(f"AOI {analysis.aoi_id} not found")

    geometry = wkb_to_geojson(aoi.geom)
    imagery = get_imagery_source()
    collection = settings.stac_default_collection

    analysis.status = AnalysisStatus.RUNNING.value
    session.commit()

    scene_a = pick_best_scene(imagery, geometry, analysis.date_a, collection)
    scene_b = pick_best_scene(imagery, geometry, analysis.date_b, collection)

    red_a, nir_a, scl_a, transform_a, crs_a = _read_bands(scene_a, geometry)
    red_b, nir_b, scl_b, transform_b, crs_b = _read_bands(scene_b, geometry)

    red_b = _align_to_reference(red_b, transform_b, crs_b, transform_a, crs_a, red_a.shape)
    nir_b = _align_to_reference(nir_b, transform_b, crs_b, transform_a, crs_a, nir_a.shape)
    scl_b = _align_to_reference(scl_b, transform_b, crs_b, transform_a, crs_a, scl_a.shape)

    ndvi_a = compute_ndvi(nir_a, red_a)
    ndvi_b = compute_ndvi(nir_b, red_b)

    valid_mask = ~(scl_cloud_mask(scl_a) | scl_cloud_mask(scl_b))
    diff = ndvi_diff(ndvi_a, ndvi_b)
    changed_mask = threshold_mask(diff, analysis.threshold) & valid_mask
    rgba = colorize_diff(diff, valid_mask, analysis.threshold)
    stats = summarize_diff(diff, changed_mask, valid_mask)

    cog_bytes = write_cog_bytes(rgba, transform_a, str(crs_a))
    s3_key = f"analyses/{analysis.id}.tif"
    put_object(s3_key, cog_bytes)

    analysis.status = AnalysisStatus.DONE.value
    analysis.s3_key = s3_key
    analysis.stats = stats
    analysis.completed_at = datetime.now(timezone.utc)
    session.commit()
