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
from app.imagery.sensor import SensorType, sensor_for_collection
from app.models.aoi import AOI
from app.models.analysis_result import AnalysisResult, DetectionStatus
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


# Found live (running a real analysis end-to-end): one run's inference call
# failed with "Server disconnected without sending a response" and NO
# corresponding request ever logged on the inference side — a stale/reset
# connection between containers (an idle keep-alive connection closed by the
# peer or the network layer between low-frequency requests), not the
# inference service actually failing. One retry on a fresh connection is
# cheap insurance against exactly that; it does NOT cover a real HTTP error
# status (raise_for_status below), which is a genuine application failure,
# not a transient network one, and is deliberately left to propagate on the
# first attempt.
_DETECT_MAX_ATTEMPTS = 2


def _detect_chips(png_chips: list[bytes]) -> list[list[dict]]:
    """One batched request for every chip (up to MAX_CHIPS), not one request
    per chip — PERF: this used to be a sequential per-chip httpx.post loop
    (up to 9 round trips, each with its own model forward pass), which meant
    a single analysis's detection step serialized 9x the network overhead
    AND 9x the per-call model overhead. services/inference's ModelBackend
    now runs one batched forward pass over the whole list (see
    ModelBackend.predict_batch) — a real throughput win on GPU, and a real
    latency win even on CPU. Returns [] immediately without a network call
    when there are no chips (an AOI whose scene read produced zero tiles)."""
    if not png_chips:
        return []
    # SEC-09: shared-secret gate on the inference service — see
    # services/inference/app/security.py.
    payload = {"images_base64": [base64.b64encode(b).decode() for b in png_chips]}
    headers = {"X-Inference-Token": settings.inference_token}

    for attempt in range(1, _DETECT_MAX_ATTEMPTS + 1):
        try:
            response = httpx.post(
                f"{settings.inference_base_url}/detect",
                json=payload,
                headers=headers,
                # One batched forward pass over up to MAX_CHIPS chips can
                # legitimately take longer than a single chip did — generous
                # headroom, especially on a CPU-only inference backend (see
                # services/inference's device setting).
                timeout=120.0,
            )
            response.raise_for_status()
            return response.json()["detections"]
        except httpx.TransportError as exc:
            if attempt >= _DETECT_MAX_ATTEMPTS:
                raise
            logger.warning(
                "inference request failed (%s: %s), retrying once on a fresh connection",
                type(exc).__name__,
                exc,
            )
    raise AssertionError("unreachable — loop above always returns or raises")


def _box_to_geojson(box_px: tuple[float, float, float, float], transform: Affine, crs: object) -> dict:
    """Chip-pixel (x0,y0,x1,y1) box -> GeoJSON Polygon in EPSG:4326."""
    x0, y0, x1, y1 = box_px
    corner_a = rowcol_to_xy(transform, y0, x0)
    corner_b = rowcol_to_xy(transform, y1, x1)
    xs_native = [corner_a[0], corner_b[0]]
    ys_native = [corner_a[1], corner_b[1]]
    lons, lats = warp_transform(crs, "EPSG:4326", xs_native, ys_native)
    return shapely_mapping(shapely_box(min(lons), min(lats), max(lons), max(lats)))


def run_placeholder_detection(session: Session, analysis: AnalysisResult) -> int:
    """Best-effort placeholder object detection over date_b's true-color
    imagery, tiled into a fixed, capped grid of chips sent to
    services/inference. The caller (app.tasks.change_detection,
    app.tasks.monitor_sweep) logs and swallows failures here — a detection
    failure shouldn't flip an already successful AnalysisResult to failed.

    Optical only: the model backends (services/inference) are trained on
    COCO/optical-Sentinel-2 imagery, not SAR amplitude data — running them
    over a SAR chip wouldn't detect real objects, it would produce
    plausible-looking noise (CLAUDE.md's "never fake a capability"). Callers
    are expected to gate on app.imagery.sensor.sensor_for_collection
    themselves (see monitor_sweep.py); this is a defensive backstop in case
    one doesn't.

    Returns the number of detections written, and on a clean run records
    DetectionStatus.OK plus that count on the analysis (0 is a real answer, not
    a failure). The caller owns the FAILED/SKIPPED cases — only it knows
    whether a raised error means "attempted and errored" vs "deliberately not
    attempted" — see app.tasks.change_detection."""
    aoi = session.get(AOI, analysis.aoi_id)
    if aoi is None:
        raise ChangeDetectionError(f"AOI {analysis.aoi_id} not found")
    if sensor_for_collection(aoi.collection) is not SensorType.OPTICAL:
        raise ChangeDetectionError(
            f"object detection is optical-only; AOI {aoi.id} uses collection "
            f"{aoi.collection!r} (no trained SAR detector exists yet)"
        )

    geometry = wkb_to_geojson(aoi.geom)
    imagery = get_imagery_source()
    scene_b = pick_best_scene(imagery, geometry, analysis.date_b, aoi.collection)
    visual, transform, crs = _read_visual(scene_b, geometry)

    chips = _tile_chips(visual, transform)
    png_chips = [_chip_to_png_bytes(tile) for tile, _ in chips]
    batch_detections = _detect_chips(png_chips)

    written = 0
    for (_tile, tile_transform), png_bytes, detections in zip(chips, png_chips, batch_detections):
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
            written += 1

    analysis.detection_status = DetectionStatus.OK.value
    analysis.detection_count = written
    analysis.detection_error = None
    session.commit()
    return written
