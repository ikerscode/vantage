# Air-gapped / offline deployment

**This document is for the deliberate air-gap install path.** Most people installing VANTAGE should just use the plain installer — it pulls what it needs from GitHub's container registry automatically on first launch, no extra download or setup. Use this path specifically when the machine running VANTAGE will have **no network access at all**, ever — see `INSTALL.md`'s "Which install do you need?" section if you haven't already decided which path applies to you.

VANTAGE's core invariant (see `CLAUDE.md`) is that it never has a hard runtime dependency on external SaaS. This install path takes that furthest: once the container images are loaded (see below), it works with networking disabled entirely, from first launch, forever.

## Two downloads, not one

The installer (`.deb`/`.AppImage`/`.dmg`/`.msi`) does **not** embed the container images — the real, measured tarball is ~2.7 GiB (see `PACKAGING_V2_REPORT.md`; it was ~6.6 GiB before that report's size fixes), still over GitHub's hard 2 GiB release-asset cap, and embedding it would balloon every installer to match even for people who don't need it. This is normal for air-gapped software distribution, not a shortcut: for this path, you get **two things from the same GitHub Release**:

1. The installer for your OS — small, fast to download, installs normally.
2. `vantage-images-1.0.0.tar.part-*` (a couple of chunks) + `vantage-images-1.0.0.tar.sha256` — the offline container-image bundle. On a **networked** machine:

   ```bash
   cat vantage-images-1.0.0.tar.part-* > vantage-images-1.0.0.tar
   sha256sum -c vantage-images-1.0.0.tar.sha256
   ```

   Then carry the reassembled `vantage-images-1.0.0.tar` to the air-gapped target via your approved media (USB, etc.) and place it in VANTAGE's data directory (see `INSTALL.md`'s table — e.g. `~/.local/share/VANTAGE` on Linux) **before first launch**. `apps/launcher/launcher-core/src/images.rs` checks that location automatically and loads it (`docker`/`podman load`, not a registry pull) on next start — see `scripts/package/save-images.sh`/`split-images.sh`.

Without this step, an air-gapped machine's install can't start: these images are never pushed anywhere reachable without network access. (A **networked** install doesn't need this at all — `images.rs` falls back to pulling the same images from GHCR automatically; see `PACKAGING_V2_REPORT.md`.)

## What "offline by default" actually means here

Once the image bundle above is loaded, everything else needs zero network access, by design:

- The placeholder ML detector's model weights are baked into its image at *build* time (`services/inference/Dockerfile`) — the running container never fetches them.
- Fonts (IBM Plex, self-hosted via `@fontsource`), the map style, and all other frontend assets are bundled into the app — no CDN fetch, ever. This is enforced two ways, not just by convention: a `Content-Security-Policy` baked into the production build (`apps/web/vite.config.ts`) restricts `connect-src`/`script-src`/`font-src` to `'self'` plus `localhost`, and Tauri's own `app.security.csp` in `apps/launcher/src-tauri/tauri.conf.json` applies the same restriction at the webview level.
- Real Sentinel-2 imagery — two real scenes, pre-fetched and cropped to a fixed demo AOI with genuine NDVI contrast between dates — ships inside the installer (`infra/demo-data/`, ~54MB). A dedicated `ImagerySource` implementation (`apps/api/app/imagery/static_catalog.py`, `IMAGERY_SOURCE=static_catalog`) reads these local files; **the actual demo AOI/analysis you see on first launch is computed by the real change-detection pipeline against this local data**, not a canned screenshot. See `PACKAGE_REPORT.md` for how this was verified.
- All services bind to `127.0.0.1` only (`infra/docker-compose.prod.yml`) — nothing on the machine is reachable from the network, which also means nothing on the machine can reach *out* through an accidentally-exposed port.

## Imagery modes

Set during the first-run wizard, stored in `${data_dir}/config/.env` as `IMAGERY_SOURCE`:

| Mode | `IMAGERY_SOURCE` | Needs internet? | What it is |
|---|---|---|---|
| **Offline (default)** | `static_catalog` | No | Bundled demo scenes only (see above). Real pipeline, fixed dataset. |
| Online | `earth_search` | Yes | Live search against Element84 Earth Search — the same v1 path `apps/api` has always used. |
| Internal catalog | `pgstac` | No (once ingested) | The v2 local/air-gapped STAC catalog seam — `apps/api/app/imagery/pgstac.py` is a deliberate `NotImplementedError` stub today (no ingestion pipeline exists yet). The config path exists so a locked-down deployment can be pointed at it the moment that lands; it does not work yet. |

Switching modes: edit `IMAGERY_SOURCE` in `${data_dir}/config/.env` and restart the app (tray menu → Restart). `STAC_API_URL` in the same file is what "online" mode points at if you need to repoint it at an internal Earth-Search-compatible endpoint instead of the public one.

## Verifying no external calls yourself

Don't take the bullet points above on faith — the fastest real check (after the image bundle from "Two downloads, not one" above has already been loaded at least once — that one step does need to have happened first, on some machine, at some point):

```bash
# with the app already running and healthy:
sudo iptables -I OUTPUT -p tcp --dport 443 -j REJECT   # or just disconnect networking
# use the app normally — explore the demo AOI, run an analysis, check a monitor
sudo iptables -D OUTPUT -p tcp --dport 443 -j REJECT    # restore
```

If you saw no failed requests in the app (everything should work identically with networking down, since default mode never needs it), that's your proof — not this document's word for it. See `PACKAGE_REPORT.md` and `OFFLINE_BUNDLE_REPORT.md` for what level of this was actually exercised during development versus left for you to confirm on your own machine.

## Re-pointing at a fully internal deployment

Everything below is an env var in `${data_dir}/config/.env` — no code change needed for any of it (same invariant as the dev `.env.example`):

| Concern | Var(s) | Air-gapped value |
|---|---|---|
| Imagery | `IMAGERY_SOURCE`, `STAC_API_URL` | `pgstac` once that seam is implemented (v2), or keep `static_catalog` with your own curated `infra/demo-data/manifest.json` |
| Object store | `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | Point at any internal S3-compatible endpoint instead of the bundled MinIO |
| Auth | `JWT_SECRET`, `JWT_ISSUER` | Real OIDC/Keycloak integration is v2 (`apps/api/app/core/security.py`) — the desktop app's single-user JWT stub is acceptable for a single-workstation tool but is explicitly not multi-user, see `COMPLIANCE.md` |
| CORS | `CORS_ALLOWED_ORIGINS` | Defaults to the Tauri webview's own origins (`tauri://localhost`, `http://tauri.localhost`) — only relevant to change if you're running the API standalone outside the launcher |

## Licensing note (Sentinel-2 imagery)

The bundled demo scenes are Copernicus Sentinel-2 data, freely redistributable under the [Copernicus Sentinel Data terms](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice). If you redistribute this installer, retain the attribution: *"Contains modified Copernicus Sentinel data, processed by ESA."*
