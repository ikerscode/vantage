FROM python:3.11-slim

# SEC-06: never run as root.
RUN groupadd --system vantage && useradd --system --gid vantage --no-create-home --shell /usr/sbin/nologin vantage

WORKDIR /app

# GPU/CPU variant switch. "cpu" (default) installs the +cpu torch/torchvision
# build (requirements.lock.txt) -- no CUDA runtime, works on any host.
# "cuda" installs requirements.cuda.lock.txt (torch/torchvision +cu126)
# instead -- the pip wheel bundles its own CUDA runtime libraries (cublas,
# cudnn, etc.), so no nvidia/cuda base image is needed here; the HOST still
# needs an NVIDIA driver new enough to report CUDA 12.6+ (driver >= 560.x)
# and nvidia-container-toolkit installed so the container runtime can pass
# the GPU through (see infra/docker-compose.gpu.yml, which sets this build
# arg and requests the device reservation together -- one without the other
# doesn't work).
# Build with: docker build --build-arg INFERENCE_VARIANT=cuda ...
# NOTE: not independently verified end-to-end against a live GPU container
# in this sandbox (no container runtime + GPU passthrough available together
# here) -- the lockfile's wheel resolution was verified for real (see
# requirements.cuda.lock.txt's compile output), the runtime behavior wasn't.
ARG INFERENCE_VARIANT=cpu

# SEC-07: hash-pinned dependencies — see apps/api/Dockerfile's comment for
# the full rationale; same mechanism, this service's own requirements*.lock.txt.
# Renamed to a common /tmp/requirements.<variant>.lock.txt shape on the way in
# so the RUN line below can select either with the one ARG, without the repo
# file itself needing a "cpu" in its name (kept as requirements.lock.txt to
# match apps/api/services/tiler's naming convention).
COPY services/inference/requirements.lock.txt /tmp/requirements.cpu.lock.txt
COPY services/inference/requirements.cuda.lock.txt /tmp/requirements.cuda.lock.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.${INFERENCE_VARIANT}.lock.txt

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
