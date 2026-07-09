# VANTAGE — Vessel Detection Report (BRIEF v1.8)

Context for this brief (see `CLAUDE.md` — unchanged by any of this): VANTAGE
is a portfolio piece for NATO/defense-adjacent hiring, not a commercial
product for distribution. That changes the licensing calculus for training
data (non-commercial/research-use datasets are now acceptable) — it changes
nothing else. The analysis-not-targeting boundary (`CLAUDE.md` §1) holds
without exception: everything below is **point/box detection of vessel
presence and location**, never targeting, fire-control, or kill-chain logic.
The honest-reporting standard from every prior brief also holds in full —
this report includes real failure modes, not just the headline numbers.

## Phase 0 — dataset research and decision

Three candidates were researched directly at source (license text, real
access mechanics, resolution fit) — not from search-result summaries.

### Candidate 1: xView3-SAR (Sentinel-1 SAR, dark-fishing detection)

- Dataset access is behind registration at [iuu.xview.us](https://iuu.xview.us/); I could not pull exact license text off the page itself — only "free and open" language, no linked legal terms. **Unconfirmed at the legal-text level.**
- A real, working pretrained model exists: [`allenai/sar_vessel_detect`](https://github.com/allenai/sar_vessel_detect) — Apache-2.0 repo, and the actual weight file downloads for real (confirmed: 121.7 MB, valid PyTorch checkpoint, not a placeholder, fetched directly from `https://ai2-prior-sarfish.s3.us-west-2.amazonaws.com/public/sarfish-models/xview3-nov20-combo8/model.pth`).
- **But**: the newer, better-documented [`allenai/vessel-detection-sentinels`](https://github.com/allenai/vessel-detection-sentinels) repo's own model cards (`docs/sentinel1_model_card.md`, `docs/sentinel2_model_card.md`) explicitly state **"License: TBD"** for the trained weights themselves — separate and distinct from the repo's Apache-2.0 code license. That's a real, unresolved ambiguity, not something I'm comfortable rounding up to "clearly fine."
- Integration cost: genuinely new modality. Sentinel-1 SAR needs a new `ImagerySource` adapter, SAR-specific preprocessing (despeckling/normalization — no NDVI/true-color equivalent), and doesn't reuse any of the existing optical pipeline. This is the "new-modality-adapter" scope the brief distinguished from a model swap.
- Verified while researching this path: `allenai/vessel-detection-sentinels`'s own Sentinel-2 model card claims Precision=.819/Recall=.790/F1=.804, **but its own "Evaluation Data" section says that evaluation ran on Sentinel-1 scenes** — an internal inconsistency in AllenAI's own documentation (likely copy-pasted from the Sentinel-1 model card and never corrected). Worth knowing if that repo is ever revisited, but not disqualifying on its own — I didn't use their model.

### Candidate 2: optical Sentinel-2 vessel datasets

- The brief's own fragmentary lead ("~1783×938px chips, ~1147 instances") is real: [Zenodo 10418786](https://zenodo.org/records/10418786), CC BY 4.0, direct 66MB download. But its annotations are CSV **points** (with length/heading attributes), not boxes.
- A better fit turned up during the same research pass: [Zenodo 15019034](https://zenodo.org/records/15019034) — "Dataset for marine vessel detection from Sentinel-2 images in the Finnish coast." **CC BY 4.0**, direct 2.6MB download (5 GeoPackage files, one per MGRS tile: 34VEM, 35VLG, 34VEN, 34WFT, 34VER), **real bounding-box annotations** (not points — confirmed directly by reading the geopackages: `POLYGON` geometries, UTM-projected, one layer per acquisition date), 8,767 annotated vessel instances across 15 Sentinel-2 scenes, confirmed 10m GSD, mean vessel diameter ~92.5m (**~9 pixels at Sentinel-2 resolution — genuinely detectable**, unlike xView's small-vehicle classes).
- A YOLOv8 model trained on this same dataset exists on HuggingFace (`mayrajeo/marine-vessel-detection-yolov8`) — confirmed **Ultralytics/AGPL-3.0**, correctly **ruled out** per `CLAUDE.md` §4's locked constraint ("Ultralytics YOLO must never be used anywhere in this codebase"). The dataset itself is unaffected by that — CC BY 4.0, independent of the disqualified model, and nothing about using the dataset requires using that model.
- Integration cost: **model-swap only**. Fine-tune the already-locked-in `torchvision.models.detection.fasterrcnn_resnet50_fpn` (BSD-3, COCO-pretrained) behind the existing `ModelBackend` interface. No new imagery adapter, no new modality — imagery comes from the same Earth Search v1 STAC catalog `apps/api` already uses at inference time.

### Candidate 3: original xView (fallback)

Confirmed CC BY-NC-SA 4.0 directly at [xviewdataset.org/terms.html](https://xviewdataset.org/terms.html). Resolution-mismatched for most of its 60 classes at Sentinel-2's 10m GSD, exactly as the brief predicted — small vehicles are sub-pixel or a handful of pixels. Not needed: a genuinely 10m-appropriate, better-licensed vessel dataset already exists (Candidate 2).

### Decision

**Selected: Candidate 2 — fine-tune `fasterrcnn_resnet50_fpn` on Zenodo 15019034.** Confirmed via user checkpoint before proceeding (see conversation). Rationale: genuinely valid at Sentinel-2 resolution (not resolution-mismatched wishful thinking), cleanest license (CC BY 4.0, no non-commercial restriction, no ambiguous "TBD" weight license), smallest integration scope (model-swap, not new-modality), and real bounding-box ground truth rather than points needing heuristic conversion.

**Sandbox feasibility, checked before committing to this scope**: this environment has a real GPU (NVIDIA RTX 4050 Laptop, 6GB VRAM, driver 595.71.05/CUDA 13.2), real network access, and 168GB free disk — genuine fine-tuning was possible here, not just planned for later.

## Phase 1 — integration

### Data pipeline (`scripts/train_vessel_detector/`, gitignored `data/`+`.venv/`, real scripts committed)

1. **`prepare_dataset.py`** downloads the 5 GeoPackages from Zenodo directly. Each has one layer per acquisition date (e.g. `34VEM.gpkg` → layers `20220515`, `20220619`, `20220721`, `20220813`), each a `GeoDataFrame` of `boat`-labeled `Polygon` geometries in the tile's native UTM CRS (EPSG:32634/32635).
2. For each tile+date, it queries **Earth Search v1** — the same public STAC catalog `apps/api/app/imagery/earth_search.py` already uses at inference time — for the matching `sentinel-2-l2a` item (by reprojecting the annotation centroid to WGS84 and filtering on `grid:code == "MGRS-{tile}"`). This deliberately avoids requiring a Copernicus Data Space Ecosystem account: both catalogs serve the same underlying ESA archive, so there was no need to introduce a second credentialed data source just for training-data prep.
3. For each matched scene, it reads a windowed region of the `visual` (true-color) COG covering that scene's annotation envelope (+1024m margin) via `/vsicurl/`, confirms the raster CRS matches the annotation CRS, then tiles the region into 512×512 chips (matching `apps/api`'s existing chip size convention in `detection_pipeline.py`) and converts each intersecting polygon into a pixel-space bounding box via the chip's affine transform.
4. **Tile `34VER` is excluded from training entirely** (`HELD_OUT_TILE = "34VER"`) — not just held-out crops of scenes the model already saw elsewhere, but three whole scenes (2022-06-17, 2022-07-12, 2022-08-26) it never touched during training.

Real run output:

```
=== TOTAL: 6475 chips ===
train (tiles != 34VER): 5314 chips, 8306 boxes
held-out (34VER): 1161 chips, 344 boxes
```

(18 scenes matched and fetched successfully — 100% match rate against Earth Search for every tile+date the annotations referenced.)

### Fine-tuning (`train.py`)

Loads `fasterrcnn_resnet50_fpn(weights=FasterRCNN_ResNet50_FPN_Weights.DEFAULT)` — the same COCO-pretrained backbone+FPN `TorchvisionFasterRCNN` already uses — replaces `roi_heads.box_predictor` with a fresh 2-class head (background/vessel), and fine-tunes for 12 epochs (SGD, lr=0.005 momentum=0.9, step decay ×0.1 at epoch 6) on the 5,314 training chips. Real run, on the sandbox's own RTX 4050 GPU:

```
epoch 1/12: avg loss = 0.1506
epoch 2/12: avg loss = 0.1132
epoch 3/12: avg loss = 0.1051
epoch 4/12: avg loss = 0.1001
epoch 5/12: avg loss = 0.0938
epoch 6/12: avg loss = 0.0898
epoch 7/12: avg loss = 0.0777   <- LR step-down
epoch 8/12: avg loss = 0.0757
epoch 9/12: avg loss = 0.0746
epoch 10/12: avg loss = 0.0740
epoch 11/12: avg loss = 0.0732
epoch 12/12: avg loss = 0.0727
saved checkpoint (165.7 MB)
```

### Wiring into `services/inference`

- **`app/models/torchvision_fasterrcnn_vessel.py`** (new): `TorchvisionFasterRCNNVessel`, same `ModelBackend` interface, same architecture, loads the fine-tuned checkpoint instead of raw COCO weights, maps class index 1 → `"vessel"`.
- **`app/models/factory.py`**: `MODEL_BACKEND=torchvision_fasterrcnn_vessel` opts in; `torchvision_fasterrcnn` (COCO placeholder) **remains the default** — confirmed unchanged by direct test (`get_model_backend()` with no env override still returns `TorchvisionFasterRCNN`). Both are real, working, selectable backends — "show both" per the brief, not a replacement.
- **`app/core/config.py`**: new `vessel_weights_path` setting.
- **Honest seam, not a silent failure**: if `MODEL_BACKEND=torchvision_fasterrcnn_vessel` is selected without the weights file present, `TorchvisionFasterRCNNVessel.__init__` raises a `FileNotFoundError` naming the missing path and pointing at `services/inference/weights/README.md` — verified directly:
  ```
  correctly raised FileNotFoundError:
  MODEL_BACKEND=torchvision_fasterrcnn_vessel was selected but no weights file
  exists at /tmp/nonexistent.pth — this is a gitignored local/build artifact
  (165.7MB), not something silently faked. See services/inference/weights/README.md
  to produce it, or switch back to MODEL_BACKEND=torchvision_fasterrcnn
  (the COCO placeholder, default).
  ```
- **`Dockerfile`**: bakes the checkpoint in via `COPY services/inference/weights/ /app/weights/` — a **directory-level** copy, deliberately not naming the `.pth` file directly. The checkpoint is 165.7MB, over GitHub's 100MB per-file push limit without git-lfs, so it's gitignored; a specific-file `COPY` would break the *default* image build (COCO-only, which needs nothing from this directory) for every checkout that doesn't have the real weights locally. The directory always contains at least `weights/README.md` (tracked), so the COPY step always succeeds; the vessel backend's own `FileNotFoundError` above is what surfaces the real gap, loudly, only when someone actually opts into it.
- **Scope boundary, stated plainly**: this pass did not push the fine-tuned image through GHCR/the release pipeline — that's a mechanical follow-up (upload the checkpoint as a release asset, `curl` it at build time, same pattern `services/inference/Dockerfile` already uses for COCO weights), not the core "prove genuine detection capability" ask this brief was about.

**Real, verified end-to-end** (not just code review) — ran the actual `app.models.factory.get_model_backend()` → `TorchvisionFasterRCNNVessel.predict()` path against a real held-out chip:

```
backend loaded: TorchvisionFasterRCNNVessel
chip 34VER_20220617_2_14: 3 ground truth boxes -> 3 DetectionBox results
  box=(325.9, 143.0, 331.5, 153.4) score=0.985 label='vessel'
  box=(239.4, 214.6, 244.6, 218.4) score=0.985 label='vessel'
  box=(238.0, 228.3, 242.2, 232.0) score=0.935 label='vessel'
```

## Phase 2 — honest evaluation on held-out imagery

All numbers below are from tile **34VER** — three full Sentinel-2 scenes (2022-06-17, 2022-07-12, 2022-08-26) the model never saw during training, not held-out crops of training scenes. 1,161 chips, 344 ground-truth vessel boxes. IoU≥0.5 greedy matching, by confidence threshold:

| Confidence ≥ | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| 0.3 | 284 | 366 | 60 | 0.437 | **0.826** | 0.571 |
| 0.5 | 274 | 265 | 70 | 0.508 | 0.797 | 0.621 |
| 0.7 | 262 | 184 | 82 | 0.587 | 0.762 | 0.663 |
| 0.9 | 234 | 94 | 110 | **0.713** | 0.680 | **0.696** |

Real overlay images (predicted boxes in red-dashed, ground truth in green, on real held-out Sentinel-2 chips) saved to `run_artifacts/vessel_detection/` (gitignored per repo convention — real run output, not committed, same as every prior brief's `run_artifacts/`).

### What it actually does well

On open water, away from coastline and archipelago clutter, the model finds vessels reliably and with high confidence — a representative dense chip (`dense_0_34VER_20220712_18_4.png`) shows 11 of 11 annotated vessels correctly detected at 0.58–0.99 confidence, tight boxes matching ground truth closely. This is genuine signal at Sentinel-2's ~10m GSD, not an artifact of the eval methodology — mean annotated vessel size (~9px) is small but not sub-pixel, and the model has clearly learned the visual signature (a small, bright/dark rectangular contrast against uniform water) rather than memorizing specific locations, since these are scenes and dates it never trained on.

### What it actually gets wrong — real failure modes, not a hedge

1. **False positives on harbor/pier infrastructure.** `false_positive_example_0_34VER_20220617_19_3.png` shows a 0.94-confidence detection directly on a pier/dock structure with no corresponding ground-truth annotation — a permanently-moored structure or quay visually similar to a vessel (rectangular, contrasting with water) at this resolution.
2. **False positives on small rocky skerries and open-water specks.** `false_positive_example_1_34VER_20220712_19_3.png` is the starker case: only 2 ground-truth vessels in this chip, but the model fires 9 additional detections at 0.58–0.98 confidence scattered across small rock outcrops (typical of the Finnish archipelago) and isolated bright specks in open water. The model has learned a general "small contrasting blob on water" cue that correctly catches real vessels but also fires on skerries, rocks, and possibly real-but-unannotated small boats (the dataset's per-date annotation coverage isn't necessarily exhaustive — a boat present but not logged for that specific pass is indistinguishable, in this evaluation, from a genuine false positive).
3. **Precision ceiling is real, not a threshold-tuning artifact.** Precision only reaches 0.71 even at a strict 0.9 confidence cutoff, and that costs meaningful recall (0.68). There's no confidence threshold in this evaluation that gets both precision and recall above ~0.8 simultaneously — the failure modes above are a genuine architecture/data limitation at this training scale (5,314 chips, single-epoch-schedule fine-tune), not a calibration problem fixable by picking a different cutoff.
4. **Annotation-quality caveat, stated plainly**: the "false positives" above are false relative to this dataset's per-date human annotations, which is a real, publicly-licensed ground truth — but it is not necessarily a complete, adjudicated census of every vessel present in every scene. Some of what's flagged as a false positive here could be a real, small vessel the original annotators didn't log for that particular pass. I have not independently re-verified individual disputed detections against higher-resolution imagery, so I'm reporting this as an open uncertainty, not resolving it in the model's favor.

### Comparison to the placeholder it sits alongside

The original `TorchvisionFasterRCNNVessel`'s sibling, `TorchvisionFasterRCNN` (COCO-pretrained, unmodified), was never expected to find vessels at all in Sentinel-2 imagery — it's trained on ground-level photos of everyday objects, and `RUN_REPORT.md`/prior briefs already documented it returning zero detections on overhead imagery as the honest, expected placeholder result. This fine-tune is a genuine step beyond that: a real, if imperfect, domain-specific capability, with real precision/recall numbers instead of a documented absence of capability. Both remain selectable side by side (`MODEL_BACKEND` env var) — the story this brief asked for is "general-purpose placeholder proving the pipeline" next to "domain-tuned model proving real capability," not one replacing the other.

## Files changed / added

- `scripts/train_vessel_detector/{prepare_dataset,train,evaluate}.py` — real, reproducible pipeline (annotation download → Earth Search fetch → chip+bbox dataset → fine-tune → held-out eval + overlays). `data/` and `.venv/` gitignored (real, large, reproducible — not meant to live in git history, consistent with this repo's existing `run_artifacts/` convention).
- `services/inference/app/models/torchvision_fasterrcnn_vessel.py` (new), `factory.py`, `core/config.py` (both edited) — new opt-in backend, COCO placeholder untouched and still default.
- `services/inference/weights/README.md` (new, tracked) — explains the gitignored checkpoint and how to reproduce it; `services/inference/Dockerfile` — directory-level `COPY` so default (COCO-only) builds are unaffected.
- `.gitignore` — `services/inference/weights/*.pth`, `scripts/train_vessel_detector/{data,.venv}/`.
- `run_artifacts/vessel_detection/*.png` — 6 real overlay images (already gitignored by existing repo convention), referenced above by filename.
