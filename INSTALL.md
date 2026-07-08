# Installing VANTAGE

This covers installing the packaged desktop app. If you're modifying the code, see the README's source-build path instead.

**Read this first**: VANTAGE is a heavy, workstation-class app, not a lightweight utility. Budget **8GB+ RAM** and **~10GB+ disk**. It also needs a container runtime (Docker or Podman) — the launcher detects this and guides you through installing one if it's missing.

**Two downloads, not one**: the installer itself is small (see sizes below), but it does **not** include the container images (PostGIS, an object store, a tiling service, an ML inference service) — that's a real, measured ~6.6 GiB, over 3x GitHub's per-file release-asset cap (see `OFFLINE_BUNDLE_REPORT.md`). You also need the `vantage-images-1.0.0.tar.part-*` chunks from the same GitHub Release — see [docs/AIRGAP.md](docs/AIRGAP.md) for the one-time reassemble-and-place step. Without it, the app cannot start (these images are never pulled from a registry).

**No phone-home**: nothing in this app calls out to any external service except imagery sources you explicitly configure (and by default, it's configured to use only bundled offline demo imagery — see [docs/AIRGAP.md](docs/AIRGAP.md)). No telemetry, no analytics, no update pings, no crash reporting that leaves your machine.

---

## System requirements

| | Minimum |
|---|---|
| RAM | 8 GB (16 GB recommended if you'll run real analyses, not just the demo) |
| Disk | 10 GB free (more if you point it at a real imagery archive later) |
| OS | Linux (recent, glibc-based), macOS 12+, or Windows 10/11 |
| Container runtime | Docker Desktop / Docker Engine, or Podman 4+ |

## Install

### Linux — `.deb`

```bash
sudo dpkg -i vantage_1.0.0_amd64.deb
```

If you don't already have a container runtime: `sudo apt install podman` (or install Docker per Docker's own instructions — the launcher works with either).

### Linux — `.AppImage` (portable, no install step)

```bash
chmod +x VANTAGE_1.0.0_amd64.AppImage
./VANTAGE_1.0.0_amd64.AppImage
```

### macOS — `.dmg`

Open the `.dmg`, drag VANTAGE to Applications. **Signing note**: this build may be unsigned/not notarized (internal distribution) — Gatekeeper will refuse to open it normally. Right-click the app → Open, or: `xattr -cr /Applications/VANTAGE.app`. A production release should carry a real Developer ID signature + notarization; see `PACKAGE_REPORT.md` for what's actually been done here.

### Windows — `.msi`

Run the installer. **Signing note**: same caveat as macOS — an unsigned `.msi`/`.exe` triggers SmartScreen ("Windows protected your PC"). Click "More info" → "Run anyway" for internal distribution, or get it Authenticode-signed for a real release.

## First run

1. VANTAGE opens to a splash screen and checks for a container runtime. If none is found, it tells you exactly what to install (see the per-OS notes above) rather than failing silently.
2. It generates unique DB/object-store/auth secrets for this install (never shared across installs, never shipped as defaults — see `PACKAGE_REPORT.md` §9).
3. It loads the container images from the offline bundle you placed in the data directory (no registry pull, ever — see `docs/AIRGAP.md` for the one-time download-and-place step this depends on) and starts the stack, showing honest progress ("starting database… loading tiler…").
4. Once every service reports healthy, the mission-console UI opens — with a bundled demo AOI already showing real Sentinel-2 imagery, even with no internet connection.

Where things live:

| OS | App | Data (DB, imagery, logs, config) |
|---|---|---|
| Linux | `/opt/VANTAGE` (deb) or wherever you placed the AppImage | `~/.local/share/VANTAGE` |
| macOS | `/Applications/VANTAGE.app` | `~/Library/Application Support/VANTAGE` |
| Windows | `%ProgramFiles%\VANTAGE` | `%APPDATA%\VANTAGE` |

## Uninstall

- **Linux (.deb)**: `sudo apt remove vantage` (or `dpkg -r vantage`). AppImage: just delete the file.
- **macOS**: drag the app to Trash.
- **Windows**: Settings → Apps → VANTAGE → Uninstall.

None of these remove your data directory (imagery/analyses/config) automatically — the app itself, not the OS uninstaller, prompts you to optionally delete it too (tray menu → uninstall flow). To remove it by hand, delete the data directory listed in the table above.

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Air-gapped / offline deployment

See [docs/AIRGAP.md](docs/AIRGAP.md).

---

## Building the installers yourself

This is what a maintainer runs to produce the artifacts above — not something an end user needs. See `PACKAGE_REPORT.md` for exactly what's been verified vs. environment-blocked in this repo's own build history, and the precise Linux system-package list needed to compile the launcher (`apps/launcher/`).

```bash
# 1. Build the frontend (bundled into the launcher, not run as a container)
cd apps/web && npm install && npm run build && cd ../..

# 2. Build the per-OS installer (run natively on each target OS — Tauri
#    does not cross-compile installers)
cd apps/launcher
npm install
npm run build   # -> src-tauri/target/release/bundle/{deb,appimage,msi,dmg}/...
cd ../..

# 3. Build + tag the container images, then bundle them for offline
#    distribution. NOT added to tauri.conf.json's bundle.resources — the
#    real tarball is ~6.6 GiB, over 3x GitHub's per-file release-asset cap
#    (see OFFLINE_BUNDLE_REPORT.md), so it ships as separate chunked
#    downloads next to the installer, not embedded inside it.
VANTAGE_VERSION=1.0.0 ./scripts/package/build-images.sh
VANTAGE_VERSION=1.0.0 ./scripts/package/save-images.sh
VANTAGE_VERSION=1.0.0 ./scripts/package/split-images.sh
# -> writes infra/vantage-images-1.0.0.tar.part-* + a .sha256 file.
#    Distribute the installer from step 2 AND every .tar.part-*/.sha256
#    file from this step together (see docs/AIRGAP.md for what the
#    end user does with them).
```

Linux build machines need (once, via your package manager — not needed at runtime by an end user, only to *compile* the launcher):

```bash
sudo apt install libglib2.0-dev libgtk-3-dev libwebkit2gtk-4.1-dev librsvg2-dev libayatana-appindicator3-dev
```

(`libdbus-1-dev` is *not* needed — `apps/launcher/src-tauri/Cargo.toml` forces a vendored, build-from-source libdbus via Cargo feature unification instead.)
