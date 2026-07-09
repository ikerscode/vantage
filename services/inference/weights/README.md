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

To produce `vessel_fasterrcnn.pth` yourself:

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
