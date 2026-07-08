#!/usr/bin/env bash
# Splits the offline image tarball (scripts/package/save-images.sh's output)
# into chunks small enough to ship as GitHub Release assets (BRIEF v1.6).
#
# Why this exists: a single GitHub Release asset has a hard 2 GiB
# (2147483648-byte) cap, confirmed against GitHub's own docs — and the real
# tarball measures ~6.6 GiB (see OFFLINE_BUNDLE_REPORT.md), over 3x too
# large for one asset. GitHub allows up to 1000 assets per release with no
# total-size cap, so N ordered chunks is the standard, legitimate way to
# ship a payload this size via Releases — the operator downloads all
# chunks once on a networked machine, concatenates them, and `docker load`s
# the result exactly as if it had been a single file.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="${VANTAGE_VERSION:-1.0.0}"
IN_PATH="${1:-$REPO_ROOT/infra/vantage-images-$VERSION.tar}"
OUT_DIR="${2:-$REPO_ROOT/infra}"
# 1900M, not 2000M: comfortably under the 2 GiB (2147483648-byte) cap even
# accounting for filesystem/transfer overhead — no reason to cut it close.
CHUNK_SIZE="${VANTAGE_CHUNK_SIZE:-1900M}"
PREFIX="$OUT_DIR/vantage-images-$VERSION.tar.part-"

echo "== splitting $IN_PATH into ${CHUNK_SIZE} chunks =="
split -b "$CHUNK_SIZE" -d -a 2 "$IN_PATH" "$PREFIX"

CHECKSUM_FILE="$OUT_DIR/vantage-images-$VERSION.tar.sha256"
(cd "$OUT_DIR" && sha256sum "$(basename "$IN_PATH")") > "$CHECKSUM_FILE"

ls -la "$PREFIX"*
n_parts=$(ls "$PREFIX"* | wc -l)
echo ""
echo "wrote $n_parts chunk(s) plus $CHECKSUM_FILE"
echo "operator reassembles with:"
echo "  cat vantage-images-$VERSION.tar.part-* > vantage-images-$VERSION.tar"
echo "  sha256sum -c vantage-images-$VERSION.tar.sha256"
echo "  docker load -i vantage-images-$VERSION.tar   # or: podman load -i ..."
