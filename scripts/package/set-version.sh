#!/usr/bin/env bash
# Stamps a real, tag-derived version into every place the launcher's build
# artifacts are named from (BRIEF v2, found for real: every one of the 15
# releases before this fix -- app-v0.1.0 through app-v0.1.14 -- left
# apps/launcher/src-tauri/tauri.conf.json's "version" field hardcoded at
# "0.1.0", which is the field Tauri's bundler actually uses to name every
# output file. The result: every single release produced a byte-different
# .deb/.AppImage/.msi/.dmg under the IDENTICAL filename
# VANTAGE_0.1.0_amd64.deb -- the exact stale-reinstall confusion hit live
# during real-device testing, where reinstalling an old cached download
# gave no filename signal that it wasn't the just-fixed build).
#
# release.yml calls this right after checkout, before any build step, with
# the version derived from the git tag itself (e.g. "app-v0.1.14" ->
# "0.1.14") -- so the tag, the GitHub Release, and the bundle filenames can
# never drift apart again.
set -euo pipefail

VERSION="${1:?usage: set-version.sh <version, e.g. 0.1.14>}"
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "error: version must be plain semver (X.Y.Z), got: $VERSION" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LAUNCHER_DIR="$REPO_ROOT/apps/launcher"

TAURI_CONF="$LAUNCHER_DIR/src-tauri/tauri.conf.json"
jq --arg v "$VERSION" '.version = $v' "$TAURI_CONF" > "$TAURI_CONF.tmp"
mv "$TAURI_CONF.tmp" "$TAURI_CONF"

# Cargo.toml's own version is APP_VERSION (main.rs's own
# env!("CARGO_PKG_VERSION")) -- shown in the running app itself and sent to
# the frontend via FrontendRuntimeConfig -- so it must move in lockstep
# with the bundle filename above, not just tauri.conf.json.
sed -i.bak "0,/^version = /s/^version = \".*\"/version = \"$VERSION\"/" "$LAUNCHER_DIR/src-tauri/Cargo.toml"
rm -f "$LAUNCHER_DIR/src-tauri/Cargo.toml.bak"

# package.json's version isn't read by anything functional today, but
# leaving it stale next to the two above that matter is its own future
# footgun (a "what version is this really" question with three answers).
PKG_JSON="$LAUNCHER_DIR/package.json"
jq --arg v "$VERSION" '.version = $v' "$PKG_JSON" > "$PKG_JSON.tmp"
mv "$PKG_JSON.tmp" "$PKG_JSON"

echo "stamped version $VERSION into:"
echo "  $TAURI_CONF"
echo "  $LAUNCHER_DIR/src-tauri/Cargo.toml"
echo "  $PKG_JSON"
