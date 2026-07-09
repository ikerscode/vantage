FROM python:3.11-slim

# SEC-06: never run as root.
RUN groupadd --system vantage && useradd --system --gid vantage --no-create-home --shell /usr/sbin/nologin vantage

WORKDIR /app

# SEC-07: hash-pinned dependencies — see apps/api/Dockerfile's comment for
# the full rationale; same mechanism, this service's own requirements.lock.txt.
COPY services/inference/requirements.lock.txt /tmp/requirements.lock.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock.txt

COPY services/inference /app
RUN pip install --no-cache-dir --no-deps .

# Bake COCO-pretrained weights into the image at BUILD time (needs internet
# in the build environment) so the running container never needs internet —
# the actual requirement for an air-gapped deployment. TORCH_HOME must be set
# BEFORE this download, and BEFORE switching to the non-root user below —
# torch's default cache dir is ~/.cache, which would resolve to /root/.cache
# (unreadable by a later non-root USER) otherwise, silently forcing a
# runtime re-download attempt that breaks the air-gap guarantee.
ENV TORCH_HOME=/app/.cache/torch
RUN mkdir -p "$TORCH_HOME" \
    && python -c "from torchvision.models.detection import fasterrcnn_resnet50_fpn; fasterrcnn_resnet50_fpn(weights='DEFAULT')"

# BRIEF v1.8: fine-tuned Sentinel-2 vessel-detection weights (opt-in via
# MODEL_BACKEND=torchvision_fasterrcnn_vessel — TorchvisionFasterRCNN/COCO
# stays the default and needs nothing from this directory). Directory-level
# COPY, not a specific-file COPY: the real vessel_fasterrcnn.pth (165.7MB,
# see weights/README.md) is gitignored, so most checkouts only have that
# README here — a specific-file COPY would fail the build entirely for
# everyone not opting into the vessel backend. This way the default build
# (COCO-only) always succeeds; TorchvisionFasterRCNNVessel itself raises a
# clear, actionable error at startup if selected without the real weights
# actually present (see app/models/torchvision_fasterrcnn_vessel.py).
COPY services/inference/weights/ /app/weights/

RUN chown -R vantage:vantage /app

# SEC-06: read_only (compose) means no writable filesystem for pyc caching
# at import time — harmless either way, but this skips even trying.
ENV PYTHONDONTWRITEBYTECODE=1

USER vantage

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
