# services/inference/weights/

This directory is where the fine-tuned Sentinel-2 vessel-detection checkpoint
(`vessel_fasterrcnn.pth`) lives locally. It's gitignored (165.7MB, over
GitHub's 100MB per-file push limit without git-lfs) — this README is the only
tracked file here, so the directory itself always exists in a fresh checkout
and the Dockerfile's `COPY services/inference/weights/ /app/weights/` step
never fails, even when the real weights aren't present.

**The default backend (`MODEL_BACKEND=torchvision_fasterrcnn`, the COCO
placeholder) never reads anything from this directory.** It only matters if
you opt into `MODEL_BACKEND=torchvision_fasterrcnn_vessel`.

**BRIEF v2.0: the published image already has it baked in.** The
`vantage-inference` image built and pushed by `release.yml`'s
`publish-images` job fetches the real checkpoint from a dedicated GitHub
Release (tag [`model-weights-v1`](https://github.com/ikerscode/vantage/releases/tag/model-weights-v1),
kept separate from `app-v*` tags so it isn't re-uploaded on every app
release) before the Docker build, so anyone pulling the published image or
installing via the launcher gets a working vessel backend with no extra
steps — just set `MODEL_BACKEND=torchvision_fasterrcnn_vessel`. The steps
below are only for building the checkpoint yourself from scratch (e.g. to
retrain on new data) or for building `services/inference`'s image locally
without going through the release pipeline.

To get `vessel_fasterrcnn.pth` for a local (non-release-pipeline) build,
download the same asset the release workflow uses instead of retraining:

```
gh release download model-weights-v1 --repo ikerscode/vantage \
  --pattern vessel_fasterrcnn.pth --dir services/inference/weights
echo "53878268a049583a40a366aade7ed00b85dd9e65b6cc745b9bbe703ef921ec2a  services/inference/weights/vessel_fasterrcnn.pth" | sha256sum -c -
```

Or reproduce it from scratch (real training run, not required for normal use):

```
cd scripts/train_vessel_detector
uv venv --python python3.11 .venv
uv pip install --python .venv/bin/python torch torchvision --index-url https://download.pytorch.org/whl/cu126
uv pip install --python .venv/bin/python geopandas pyogrio shapely pyproj rasterio pystac-client requests matplotlib
.venv/bin/python3 prepare_dataset.py   # downloads Zenodo 15019034 annotations + fetches matching Sentinel-2 scenes from Earth Search
.venv/bin/python3 train.py             # fine-tunes fasterrcnn_resnet50_fpn, writes data/vessel_fasterrcnn.pth
cp data/vessel_fasterrcnn.pth ../../services/inference/weights/vessel_fasterrcnn.pth
```

See `VESSEL_DETECTION_REPORT.md` (repo root) for the real training run, held-out
evaluation numbers, and honest failure-mode characterization.
