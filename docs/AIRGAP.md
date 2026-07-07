# Air-gapped / offline deployment

VANTAGE's core invariant (see `CLAUDE.md`) is that it never has a hard runtime dependency on external SaaS. The packaged desktop app takes this further: the **default** installer configuration works with networking disabled entirely, from first launch.

## What "offline by default" actually means here

- The installer bundles the container images themselves (`docker`/`podman load`, not a registry pull) — see `scripts/package/save-images.sh` / `apps/launcher/launcher-core/src/images.rs`.
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

Don't take the bullet points above on faith — the fastest real check:

```bash
# with the app already running and healthy:
sudo iptables -I OUTPUT -p tcp --dport 443 -j REJECT   # or just disconnect networking
# use the app normally — explore the demo AOI, run an analysis, check a monitor
sudo iptables -D OUTPUT -p tcp --dport 443 -j REJECT    # restore
```

If you saw no failed requests in the app (everything should work identically with networking down, since default mode never needs it), that's your proof — not this document's word for it. See `PACKAGE_REPORT.md` for what level of this was actually exercised during development versus left for you to confirm on your own machine.

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
