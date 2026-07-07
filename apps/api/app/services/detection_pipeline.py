import base64
import io
import logging
import uuid

import httpx
import numpy as np
import rasterio
from affine import Affine
from PIL import Image
from rasterio.warp import transform as warp_transform
from rasterio.warp import transform_bounds
from shapely.geometry import mapping as shapely_mapping
from shapely.geometry import shape
from shapely.geometry import box as shapely_box
from sqlalchemy.orm import Session

from app.core.config import settings
from app.imagery.factory import get_imagery_source
from app.models.aoi import AOI
from app.models.analysis_result import AnalysisResult
from app.models.detection import Detection
from app.schemas.geo import geojson_to_wkb, wkb_to_geojson
from app.services.change_detection_pipeline import ChangeDetectionError, pick_best_scene
from app.services.storage import put_object
from vantage_geo.transform import bounds_to_window, rowcol_to_xy

logger = logging.getLogger(__name__)

# Fixed-grid chip tiling, capped — genuinely placeholder-scale (see
# services/inference), not blob-detection on the change mask.
CHIP_SIZE = 512
MAX_CHIPS = 9


def _read_visual(scene, aoi_geometry_4326: dict) -> tuple[np.ndarray, Affine, object]:
    if "visual" not in scene.assets:
        raise ChangeDetectionError(f"scene {scene.id} is missing the 'visual' asset")
    with rasterio.open(scene.assets["visual"]) as src:
        bounds_in_crs = transform_bounds("EPSG:4326", src.crs, *shape(aoi_geometry_4326).bounds)
        window = bounds_to_window(src.transform, bounds_in_crs)
        visual = src.read([1, 2, 3], window=window, boundless=True, fill_value=0)
        window_transform = src.window_transform(window)
        crs = src.crs
    return visual, window_transform, crs


def _tile_chips(visual: np.ndarray, transform: Affine) -> list[tuple[np.ndarray, Affine]]:
    _, height, width = visual.shape
    chips = []
    for row0 in range(0, height, CHIP_SIZE):
        for col0 in range(0, width, CHIP_SIZE):
            if len(chips) >= MAX_CHIPS:
                return chips
            tile = visual[:, row0 : row0 + CHIP_SIZE, col0 : col0 + CHIP_SIZE]
            if tile.shape[1] == 0 or tile.shape[2] == 0:
                continue
            chips.append((tile, transform * Affine.translation(col0, row0)))
    return chips


def _chip_to_png_bytes(chip: np.ndarray) -> bytes:
    rgb = np.moveaxis(chip, 0, -1)  # (bands, H, W) -> (H, W, bands)
    buffer = io.BytesIO()
    Image.fromarray(rgb, mode="RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _detect_chip(png_bytes: bytes) -> list[dict]:
    # SEC-09: shared-secret gate on the inference service — see
    # services/inference/app/security.py.
    response = httpx.post(
        f"{settings.inference_base_url}/detect",
        json={"image_base64": base64.b64encode(png_bytes).decode()},
        headers={"X-Inference-Token": settings.inference_token},
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()["detections"]


def _box_to_geojson(box_px: tuple[float, float, float, float], transform: Affine, crs: object) -> dict:
    """Chip-pixel (x0,y0,x1,y1) box -> GeoJSON Polygon in EPSG:4326."""
    x0, y0, x1, y1 = box_px
    corner_a = rowcol_to_xy(transform, y0, x0)
    corner_b = rowcol_to_xy(transform, y1, x1)
    xs_native = [corner_a[0], corner_b[0]]
    ys_native = [corner_a[1], corner_b[1]]
    lons, lats = warp_transform(crs, "EPSG:4326", xs_native, ys_native)
    return shapely_mapping(shapely_box(min(lons), min(lats), max(lons), max(lats)))


def run_placeholder_detection(session: Session, analysis: AnalysisResult) -> None:
    """Best-effort placeholder object detection over date_b's true-color
    imagery, tiled into a fixed, capped grid of chips sent to
    services/inference. The caller (app.tasks.change_detection) logs and
    swallows failures here — a detection failure shouldn't flip an already
    successful AnalysisResult to failed."""
    aoi = session.get(AOI, analysis.aoi_id)
    if aoi is None:
        raise ChangeDetectionError(f"AOI {analysis.aoi_id} not found")

    geometry = wkb_to_geojson(aoi.geom)
    imagery = get_imagery_source()
    scene_b = pick_best_scene(imagery, geometry, analysis.date_b, settings.stac_default_collection)
    visual, transform, crs = _read_visual(scene_b, geometry)

    for tile, tile_transform in _tile_chips(visual, transform):
        png_bytes = _chip_to_png_bytes(tile)
        detections = _detect_chip(png_bytes)
        if not detections:
            continue

        chip_key = f"detections/{uuid.uuid4()}.png"
        put_object(chip_key, png_bytes, content_type="image/png")

        for det in detections:
            bbox_geojson = _box_to_geojson(tuple(det["box"]), tile_transform, crs)
            session.add(
                Detection(
                    analysis_result_id=analysis.id,
                    bbox=geojson_to_wkb(bbox_geojson),
                    label=det["label"],
                    score=det["score"],
                    chip_s3_key=chip_key,
                )
            )
    session.commit()
