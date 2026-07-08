# Installing VANTAGE

This covers installing the packaged desktop app. If you're modifying the code, see the README's source-build path instead.

**Read this first**: VANTAGE is a heavy, workstation-class app, not a lightweight utility. Budget **8GB+ RAM** and **~10GB+ disk**. It also needs a container runtime (Docker or Podman) — the launcher detects this and guides you through installing one if it's missing.

## Which install do you need?

There are **two real, different install paths** — pick based on whether the machine running VANTAGE will have internet access, not just habit:

| | **Thin / online install** | **Air-gap bundle** |
|---|---|---|
| **Who it's for** | Almost everyone. If this machine has (or will briefly have) internet access, use this. | Only genuinely air-gapped deployments — the target machine has *no* network access, ever. |
| **What you download** | Just the installer for your OS (60 MB – ~1.3 GB, see sizes below). | The installer **plus** a separate ~2.7 GiB chunked image bundle from the same GitHub Release. |
| **First launch** | Automatically pulls the container images from GHCR (GitHub's container registry) over the network — a one-time download, then cached locally. | Loads the images from the bundle you downloaded and placed in the data directory beforehand — no network involved at any point. |
| **If it can't get images** | Fails with a clear error telling you what to do (get network access, or fall back to the air-gap bundle) — never a silent hang. | N/A — the bundle is already there. |

If you're not sure, you almost certainly want the **thin install** — just download the installer and run it. The air-gap bundle exists specifically for the case where downloading anything on the target machine itself is not possible or not allowed. See [docs/AIRGAP.md](docs/AIRGAP.md) for that path's full instructions.

**No phone-home either way**: nothing in this app calls out to any external service except imagery sources you explicitly configure (and by default, it's configured to use only bundled offline demo imagery) and, for the thin install, the one-time GHCR image pull on first launch. No telemetry, no analytics, no update pings, no crash reporting that leaves your machine.

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
3. It gets the container images, however they need to get there:
   - **Air-gap bundle present** (you followed [docs/AIRGAP.md](docs/AIRGAP.md) and placed the reassembled tarball in your data directory first): loads from there, no network involved.
   - **No bundle, network available** (the normal thin-install case): pulls the images from GitHub's container registry automatically — a one-time download, then cached locally for every future launch.
   - **Neither** (no bundle, no network): fails immediately with a clear message telling you to either get network access or download the air-gap bundle — it does not hang silently trying to guess.
4. Once every service reports healthy, the mission-console UI opens — with a bundled demo AOI already showing real Sentinel-2 imagery, even with no internet connection (the demo imagery itself is bundled in the installer either way — only the container *images* differ between the two install paths).

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

Only if the target machine has no network access at all — most installs don't need this. See [docs/AIRGAP.md](docs/AIRGAP.md).

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

# 3. Build + tag the container images.
VANTAGE_VERSION=1.0.0 ./scripts/package/build-images.sh

# 4. Push them to GHCR — this is what makes the THIN install work: a
#    normal install pulls these automatically on first launch, no bundle
#    needed. (One-time operator step required before this is reachable by
#    an anonymous pull: GHCR packages default to private regardless of
#    repo visibility — see PACKAGING_V2_REPORT.md.)
for img in vantage-api vantage-tiler vantage-inference vantage-pgstac-migrate; do
  docker tag "$img:1.0.0" "ghcr.io/ikerscode/$img:1.0.0"
  docker push "ghcr.io/ikerscode/$img:1.0.0"
done

# 5. Bundle the same images for the AIR-GAP install path. NOT added to
#    tauri.conf.json's bundle.resources — the real tarball is ~2.7 GiB
#    (down from 6.6 GiB — see PACKAGING_V2_REPORT.md), still over
#    GitHub's per-file release-asset cap, so it ships as separate chunked
#    downloads next to the installer, not embedded inside it.
VANTAGE_VERSION=1.0.0 ./scripts/package/save-images.sh
VANTAGE_VERSION=1.0.0 ./scripts/package/split-images.sh
# -> writes infra/vantage-images-1.0.0.tar.part-* + a .sha256 file.
#    Distribute the installer from step 2 on its own for the thin path,
#    or the installer AND every .tar.part-*/.sha256 file together for the
#    air-gap path (see docs/AIRGAP.md for what the end user does with them).
```

Linux build machines need (once, via your package manager — not needed at runtime by an end user, only to *compile* the launcher):

```bash
sudo apt install libglib2.0-dev libgtk-3-dev libwebkit2gtk-4.1-dev librsvg2-dev libayatana-appindicator3-dev
```

(`libdbus-1-dev` is *not* needed — `apps/launcher/src-tauri/Cargo.toml` forces a vendored, build-from-source libdbus via Cargo feature unification instead.)
