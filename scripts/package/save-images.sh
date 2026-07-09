#!/usr/bin/env bash
# Saves every image the packaged app needs into ONE tarball for fully
# offline installs (BRIEF v1.3 §5). Run after build-images.sh, by a
# maintainer, with internet access; the resulting tarball is what actually
# ships inside the installer (loaded by the launcher via `podman/docker
# load`, never re-pulled — see apps/launcher/launcher-core/src/images.rs).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME="${VANTAGE_CONTAINER_RUNTIME:-docker}"
VERSION="${VANTAGE_VERSION:-1.0.0}"
OUT_PATH="${1:-$REPO_ROOT/infra/vantage-images-$VERSION.tar}"

IMAGES=(
  "vantage-api:$VERSION"
  "vantage-tiler:$VERSION"
  "vantage-inference:$VERSION"
  "vantage-pgstac-migrate:$VERSION"
  # Fully-qualified, matching build-images.sh's pull and
  # docker-compose.prod.yml's image: defaults (BRIEF v1.8) — must be the
  # exact same tag string build-images.sh pulled under, or `podman/docker
  # load` restores them under a name compose no longer looks for.
  "docker.io/postgis/postgis:16-3.4-alpine"
  "docker.io/library/redis:7-alpine"
  "docker.io/minio/minio:latest"
  "docker.io/minio/mc:latest"
)

echo "== saving ${#IMAGES[@]} images to $OUT_PATH =="
"$RUNTIME" save -o "$OUT_PATH" "${IMAGES[@]}"

size_mb=$(du -m "$OUT_PATH" | cut -f1)
echo "wrote $OUT_PATH (${size_mb} MB)"
echo "this file is what apps/launcher/src-tauri/tauri.conf.json's bundle.resources ships inside the installer."
