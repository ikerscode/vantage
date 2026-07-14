# SAR support + Monitor auto-detection + GPU/optimization pass

This report follows this repo's established convention (see `CLAUDE.md` §3, `SECURITY_FIXES_REPORT.md`, `VESSEL_DETECTION_REPORT.md`): state what was actually done, how it was actually verified, and what's honestly still open — not asserted from memory.

## 1. What this adds

Two features, requested together, plus a hardware-driven optimization pass:

1. **Automated object detection on Monitor change** — a monitor that finds a real change now automatically runs object detection over the post-change scene, so an alert shows *what* changed, not just that something did.
2. **Sentinel-1 GRD (SAR) support** — a second sensor an AOI can be tracked with, all the way through: imagery search, change detection, tiling/visualization, and the frontend UI.
3. **GPU/CUDA inference path + concurrency hardening** — the object detector can now run on GPU, and both the inference service and the Celery worker are bounded so concurrent load can't overrun the reference deployment target (a 6GB laptop GPU, ~14GB RAM).

## 2. Design decisions and why

### Sensor is an AOI-level property, not a global setting
Before this change, the whole app operated against one hardcoded `settings.stac_default_collection`. `AOI.collection` (new column, default `sentinel-2-l2a`) makes sensor a per-AOI choice, fixed at creation (`app/imagery/sensor.py` is the single dispatch point every pipeline/router keys off of — `sensor_for_collection`, `default_collection_for`, `default_change_threshold_for`). An AOI is drawn once for a sensor and reused across every Explore/Analyze/Monitor use of it; changing sensor after creation isn't supported (would silently invalidate prior analyses' comparability).

### SAR change detection: log-ratio dB, not calibrated sigma-naught
`packages/geo/src/vantage_geo/sar.py` despeckles (median filter) then converts VV amplitude to a relative dB scale (`to_amplitude_db`) and diffs the two dates. This is **not** radiometrically calibrated backscatter — that needs a calibration LUT from the product's own metadata, which isn't fetched. What it *is* correct for: a relative log-ratio change metric, which is standard practice for simple SAR amplitude change detection and doesn't need absolute calibration (an unknown-but-shared calibration constant cancels out in the difference).

`threshold_mask`/`colorize_diff`/`summarize_diff` (`vantage_geo/diff.py`) turned out to already be unit-agnostic — they operate on a plain float diff array and boolean masks with no NDVI-specific assumption. SAR reuses them directly rather than duplicating the same threshold/colorize/stats logic for a second unit. Verified via `packages/geo/tests/test_sar.py`'s `test_sar_diff_reuses_diff_pys_shared_threshold_colorize_and_summary_math`.

### The one real SAR confound this does NOT fully correct: orbit geometry
Two Sentinel-1 scenes shot from different orbit directions (ascending/descending) have different viewing/incidence geometry, which shifts absolute backscatter independent of any real ground change — plain amplitude change detection has no way to correct for this without terrain/incidence-angle correction, which is out of scope here. The mitigation: `pick_best_sar_scene` (`sar_change_detection_pipeline.py`) prefers a same-orbit-direction match for date_b against date_a, falling back to any covering scene if none exists on that date. The result is recorded honestly, not silently absorbed: `AnalysisResult.stats["orbit_state_matched"]` is `True`/`False`/`None` (`None` when orbit metadata wasn't available at all). Verified via `apps/api/tests/test_sar_pipeline.py`.

### No object detection for SAR — a deliberate gap, not an oversight
The bundled detectors (COCO-pretrained and the vessel fine-tune) are trained on optical imagery. Running them against SAR amplitude chips wouldn't detect real objects — it would produce plausible-looking noise, which CLAUDE.md §3 calls out as worse than not doing it at all. `detection_pipeline.run_placeholder_detection` raises `ChangeDetectionError` if ever called for a non-optical AOI (defensive backstop); the real gate is `monitor_sweep.py`'s `_should_run_detection`, which only fires for `SensorType.OPTICAL`. The frontend's `LayersControl` disables the Detections toggle for a SAR AOI with an explicit note, rather than leaving a control that can never do anything.

### Monitor auto-detection only runs when there's something to characterize
`Monitor.detect_on_change` (new column, default `True`) plus a sensor check (`_should_run_detection` in `monitor_sweep.py`) gate the new behavior: detection only runs when a sweep actually found change (`changed_pixel_count > 0`), not on every tick. This both matches what an analyst actually wants (characterize real change, don't spend compute on nothing) and bounds GPU/CPU load — a monitor sweeping hourly with no change most of the time adds ~zero extra inference load.

### Batched chip inference, not N sequential requests
`detection_pipeline.py` used to POST one chip at a time to `services/inference` (up to 9 sequential round trips, each with its own model forward pass). `ModelBackend.predict_batch` now takes a list of images and torchvision's detection models run one batched forward pass over all of them in a single call — a real throughput win on GPU (kernel-launch/memory-transfer overhead amortizes across the batch) and a real latency win even on CPU. `/detect`'s request/response schemas changed to `images_base64: list[str]` / `detections: list[list[DetectionBox]]` accordingly (internal, first-party contract between apps/api and services/inference — no back-compat shim needed, both sides changed together).

### GPU inference + why the container itself needs no CUDA toolkit
`services/inference/requirements.cuda.lock.txt` is a real, hash-pinned lockfile (pip-compile'd against `download.pytorch.org/whl/cu126`) — an opt-in build variant selected via the Dockerfile's `INFERENCE_VARIANT` build arg (default stays `cpu`). The CUDA pip wheel bundles its own CUDA runtime libraries, so the image needs no `nvidia/cuda` base and the host needs no CUDA toolkit installed — only a driver reporting CUDA 12.6+ (driver ≥ 560.x) and `nvidia-container-toolkit` for device passthrough. `infra/docker-compose.gpu.yml` is an opt-in override (`docker compose -f docker-compose.yml -f docker-compose.gpu.yml up`) — the base compose files stay CPU-only by default so nothing that works today (including CI, which has no GPU) regresses.

### Concurrency bounded on both sides of the GPU
Two independent, complementary caps, both aimed at the same real risk — a small (6GB) GPU getting asked to do more at once than it has memory for:
- **services/inference**: `/detect` is a sync FastAPI route, which Starlette runs in a thread pool — two concurrent requests really can call `predict_batch` on two threads at once against the same model/GPU. A `threading.Lock` around the model call serializes actual inference so peak GPU memory never exceeds one batch's worth, regardless of how many requests arrive concurrently.
- **apps/api's Celery worker**: `--concurrency` now defaults to 2 (was unset, i.e. one process per CPU core — 12 on the reference i5-12450HX) via `CELERY_WORKER_CONCURRENCY`. Each concurrent change-detection task holds a full windowed raster read in memory; this is a single-workstation app (already the compose files' own framing), not a shared server, and a default of 12 concurrent tasks on a laptop with modest free RAM is a real way to make the whole machine crawl, not just a container.

## 3. What's verified vs. honestly not (this sandbox has no Docker/GPU passthrough together, and no live network access to Earth Search from here — see `CLAUDE.md`-adjacent memory on sandbox limits)

**Verified for real, in this session:**
- `packages/geo`: full test suite passes (23 tests, including 9 new SAR-specific ones).
- `apps/api`: full test suite passes (66 tests — new: `test_imagery_sensor.py`, `test_sar_pipeline.py`, `test_monitor_sweep.py`, plus fixed/extended `test_schemas.py` for the widened threshold bound and new `collection`/`detect_on_change` fields).
- `services/inference`: new `test_detect_router.py` passes against a fake `ModelBackend` (the batching/ordering contract, not real model accuracy — that needs real weights, see `VESSEL_DETECTION_REPORT.md`).
- Every touched Python module actually imports cleanly (`python -c "import ..."` against each service's real venv, not just a syntax check).
- `requirements.cuda.lock.txt` was genuinely `pip-compile`'d (not hand-authored) against the real PyPI/PyTorch indexes, with real hashes, using a Python 3.11 interpreter matching the Dockerfile's base image (an earlier attempt under Python 3.14 was caught and redone — cross-version resolution can pick different wheels).
- `apps/api/requirements.lock.txt`'s regeneration (adding `scipy` for SAR despeckling) was diffed line-by-line against the original — only `scipy` was added, no incidental version drift.
- `infra/docker-compose.yml`, `docker-compose.prod.yml`, and `docker-compose.gpu.yml` all `config`-validate individually and the GPU overlay merges onto the base file exactly as intended (`build.args`, `deploy.resources.reservations.devices`, and `environment` all confirmed in the resolved output) — checked with the `podman-compose` available in this sandbox.
- Frontend: `tsc -b` and `npm run build` both succeed with the new SAR types/components wired in.
- Alembic migration `0004` was written following the exact pattern of `0002`/`0003` (server_default on both new columns so existing rows backfill cleanly) — see §4 for why it wasn't run against a live Postgres.

**NOT verified here (stated plainly, not glossed over):**
- No live GPU container run — this sandbox doesn't have a container runtime and GPU passthrough available together, so the CUDA image build/run, `nvidia-container-toolkit` interaction, and the read-only-filesystem-vs-CUDA-JIT-cache edge case (`docker-compose.gpu.yml`'s own comment) are unverified end to end.
- No live tile fetch against a real Sentinel-1 scene — `sarAmplitudeTilejsonUrl`/`sarFalseColorTilejsonUrl`'s `rescale` values are a documented starting point, not tuned against a real tile response (no outbound network to Earth Search from this session's frontend testing). Recalibrate against a live scene before relying on the exact contrast.
- No live Postgres — the migration's SQL shape follows the established pattern exactly, but wasn't run against a real database in this session (see `CLAUDE.md`-adjacent memory: this sandbox has no Docker/Postgres/sudo).
- UI wiring (AOI sensor picker, LayersControl's SAR base layers, the Detections-disabled note) was verified via `tsc`/build only, not a live browser click-through.

## 4. Files touched (brief map, not exhaustive — see the diff)

- **Data model**: `apps/api/app/models/{aoi,monitor}.py`, `alembic/versions/0004_*.py`, `schemas/{aoi,monitor,analysis_result}.py`, `routers/{aois,analyses}.py`
- **Sensor dispatch**: `apps/api/app/imagery/sensor.py` (new), `imagery/base.py` (+`orbit_state`), `imagery/earth_search.py` (+SAR asset keys)
- **Pipelines**: `services/change_detection_pipeline.py` (dispatcher + renamed `_execute_optical_change_detection`/`align_to_reference`), `services/sar_change_detection_pipeline.py` (new), `services/detection_pipeline.py` (batching + optical-only guard), `tasks/monitor_sweep.py` (auto-detection gate + sensor-aware thresholds/collections)
- **Geo primitives**: `packages/geo/src/vantage_geo/sar.py` (new) + `tests/test_sar.py`
- **Inference service**: `schemas.py`, `routers/detect.py` (+lock), `models/{base,torchvision_fasterrcnn,torchvision_fasterrcnn_vessel}.py` (batched `predict_batch`), `requirements-cuda.in`/`requirements.cuda.lock.txt` (new), `Dockerfile` (`INFERENCE_VARIANT` arg), `core/config.py` (comment only)
- **Infra**: `infra/docker-compose.yml`/`docker-compose.prod.yml` (`--concurrency`), `docker-compose.gpu.yml` (new)
- **Frontend**: `lib/sensor.ts` (new), `lib/tileUrl.ts` (+SAR URL builders), `store/analysisStore.ts` (+SAR layer ids), `api/{types,aois,stac}.ts`, `components/{AOIPanel,TemporalScrubber,LayersControl,MapCanvas}.tsx`, `styles.css` (`.aoi-sensor-toggle`)
- **Backend tests**: `apps/api/tests/{test_imagery_sensor,test_sar_pipeline,test_monitor_sweep}.py` (new), `test_schemas.py` (extended)
- **Inference tests**: `services/inference/tests/test_detect_router.py` (new — first test file for this service)
