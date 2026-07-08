#!/usr/bin/env bash
# Builds and tags every image the packaged app needs (BRIEF v1.3 §4, §8).
# Run by a maintainer building an installer — needs internet (base image
# pulls, torch/model weight download baked into the inference image) and a
# container runtime. NOT run by end users; the launcher only ever loads
# already-built images from the offline tarball this produces (see
# save-images.sh), never builds.
#
# NOT run in this repo's CI/sandbox history — no container runtime is
# available there (see PACKAGE_REPORT.md). Every command below is exactly
# what scripts/smoke.sh's equivalent docker-compose.yml build step already
# does per-service; this just also tags with an explicit, pinned version
# instead of docker-compose's implicit dev tag.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME="${VANTAGE_CONTAINER_RUNTIME:-docker}"  # or: podman
VERSION="${VANTAGE_VERSION:-1.0.0}"

echo "== building with $RUNTIME, tagging version $VERSION =="

"$RUNTIME" build -t "vantage-api:$VERSION" -f "$REPO_ROOT/apps/api/Dockerfile" "$REPO_ROOT"
"$RUNTIME" build -t "vantage-tiler:$VERSION" -f "$REPO_ROOT/services/tiler/Dockerfile" "$REPO_ROOT"
"$RUNTIME" build -t "vantage-inference:$VERSION" -f "$REPO_ROOT/services/inference/Dockerfile" "$REPO_ROOT"
# SEC-01/SEC-07: pypgstac baked in at build time (hash-pinned), not a
# runtime pip install against a bare python:3.11-slim — see
# infra/pgstac-migrate/Dockerfile.
"$RUNTIME" build -t "vantage-pgstac-migrate:$VERSION" -f "$REPO_ROOT/infra/pgstac-migrate/Dockerfile" "$REPO_ROOT"

# Third-party base images — pulled (not built) so save-images.sh can bundle
# them too; docker-compose.prod.yml references these exact tags.
"$RUNTIME" pull postgis/postgis:16-3.4-alpine
"$RUNTIME" pull redis:7-alpine
"$RUNTIME" pull minio/minio:latest
"$RUNTIME" pull minio/mc:latest

echo ""
echo "== resolving local content digests for pinning =="
for image in "vantage-api:$VERSION" "vantage-tiler:$VERSION" "vantage-inference:$VERSION"; do
  digest="$("$RUNTIME" image inspect "$image" --format '{{.Id}}')"
  echo "$image -> $digest"
done

cat <<EOF

Build complete. Next steps:
  1. Run scripts/package/save-images.sh to produce the offline tarball.
  2. Set VANTAGE_API_IMAGE/VANTAGE_TILER_IMAGE/VANTAGE_INFERENCE_IMAGE in the
     installer's build config to "vantage-api:$VERSION" etc. (or the pinned
     @sha256 digests printed above, for a fully immutable reference — see
     docker-compose.prod.yml's header comment on why this repo doesn't ship
     a registry-resolved digest: these images are never pushed to a
     registry, only built-and-loaded locally).
EOF
