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
  "postgis/postgis:16-3.4-alpine"
  "redis:7-alpine"
  "minio/minio:latest"
  "minio/mc:latest"
)

echo "== saving ${#IMAGES[@]} images to $OUT_PATH =="
"$RUNTIME" save -o "$OUT_PATH" "${IMAGES[@]}"

size_mb=$(du -m "$OUT_PATH" | cut -f1)
echo "wrote $OUT_PATH (${size_mb} MB)"
echo "this file is what apps/launcher/src-tauri/tauri.conf.json's bundle.resources ships inside the installer."
