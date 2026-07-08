# VANTAGE

A satellite-imagery intelligence workbench for defense/ISR analysts. Analysts define an AOI, explore the imagery archive, run change detection + object detection, and stand up monitors that alert on change. Mission-console UX — the UI floats over a full-bleed map, not a SaaS dashboard.

See `CLAUDE.md` for the always-on architectural context (invariants, conventions) that governs this codebase.

## Install the app vs. run from source

**Most users**: download a per-OS installer and run it — no dev environment needed. See **[INSTALL.md](INSTALL.md)**, and **[docs/AIRGAP.md](docs/AIRGAP.md)** for fully-offline/air-gapped deployment (two downloads, not one — the installer itself is small; the ~6.6 GiB container-image bundle is a separate chunked download from the same GitHub Release, see `OFFLINE_BUNDLE_REPORT.md`). The installer bundles a desktop launcher (Tauri) that brings up the same container stack described below, plus bundled demo Sentinel-2 imagery so that once the image bundle is loaded, the app works with no internet at all.

**Contributors / anyone modifying the code**: keep reading — this section is the source-build path.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2 + GeoAlchemy2, Alembic, pydantic-settings |
| Data | PostgreSQL 16 + PostGIS 3.4 + pgstac, SRID 4326 |
| Async jobs | Celery + Redis (+ celery-beat) |
| Object store | S3 API (MinIO locally), boto3 |
| Tiling | TiTiler (rio-tiler) — dynamic COG/STAC tiling, no pre-rendering |
| Catalog | STAC — Element84 Earth Search v1, `sentinel-2-l2a`, public COGs |
| Inference | Separate FastAPI service, `ModelBackend` interface, CPU default / GPU-ready |
| Frontend | React 18 + TS + Vite, MapLibre GL + deck.gl, Zustand, TanStack Query |
| Auth | Minimal OIDC-shaped JWT stub (v1), self-hosted Keycloak intended for prod |

## Layout

```
apps/api        FastAPI backend — AOIs, STAC search, change detection, monitors, events, detections
apps/web        React HUD (MapCanvas, TemporalScrubber, AOIPanel, LayersControl, ResultsFeed, CommandBar, Inspector)
apps/launcher   Desktop launcher (Tauri) — packages the stack into per-OS installers, see INSTALL.md
services/tiler  TiTiler wrapper — /cog (single-file COGs) + /stac (multi-asset STAC band math, e.g. NDVI)
services/inference  Placeholder object detector (torchvision Faster R-CNN, COCO-pretrained)
packages/geo    Pure geospatial functions — NDVI, cloud masking, change diff, pixel↔geo transforms, chipping
infra           docker-compose.yml (dev), docker-compose.prod.yml (packaged app), .env.example
scripts/package Offline-installer build scripts — fetch demo data, build/save/load images
```

## Quick start

```bash
cp infra/.env.example infra/.env
docker compose -f infra/docker-compose.yml up --build
```

Brings up `db` (Postgres+PostGIS, plus a one-shot `pgstac-migrate`), `redis`, `minio` (plus a one-shot bucket-init), `api` (port 8000), `worker`, `beat`, `tiler` (port 8001), and `inference`. Migrations run via the one-shot `api-migrate` service before `api`/`worker`/`beat` start.

The frontend isn't part of the compose stack yet (see `apps/web`'s own section below) — run it separately:

```bash
cd apps/web
cp .env.example .env
npm install
npm run dev
```

Loads over a dark map at `http://localhost:5173` and hits `/api/health` on load (via the dev-token bootstrap).

### Smoke test

1. `curl http://localhost:8000/api/health` → `{"status": "ok"}`
2. `curl -X POST http://localhost:8000/api/auth/dev-token` → capture `access_token`
3. Create an AOI, `POST /api/stac/search` against it, `POST /api/analyses` with two dates from the results
4. Poll `GET /api/analyses/{id}` until `status == "done"`, then fetch its `tilejson_url`

## Air-gap repoint

VANTAGE is meant to be self-hostable with no hard runtime dependency on external SaaS in the core path. Everything below is an env var — nothing requires a code change to repoint.

| Concern | v1 default | Air-gapped repoint |
|---|---|---|
| Imagery source | `IMAGERY_SOURCE=earth_search` hitting `STAC_API_URL` (public Earth Search) | `IMAGERY_SOURCE=pgstac` once a local-catalog `ImagerySource` implementation exists (`apps/api/app/imagery/pgstac.py` is a marked `TODO(v2)` seam — the `pgstac` schema is already provisioned by `infra`'s `pgstac-migrate` service, but nothing ingests into it yet) |
| Object store | MinIO via `S3_ENDPOINT_URL`/`S3_ACCESS_KEY_ID`/etc. | Point at any internal S3-compatible endpoint |
| Tiler | `services/tiler` reads Earth Search COGs via GDAL `/vsicurl/` and MinIO via `/vsis3/` | Once imagery is local (pgstac + internal object store), `/vsicurl/` traffic disappears entirely — no code change, it's a consequence of where the COGs actually live |
| Auth | Dev JWT stub (`apps/api/app/core/security.py`, single hardcoded user, real signature/expiry verification) | Swap the HS256 shared-secret verification for RS256 + JWKS against a self-hosted Keycloak issuer — `get_current_user`'s signature doesn't change, only its body |
| Inference | `services/inference`'s Dockerfile bakes COCO weights into the image at *build* time | The running container never needs internet — this is already air-gap-ready as built, as long as the image is built somewhere with connectivity first |

## Known v1 scope cuts (see `COMPLIANCE.md` for the licensing/invariant angle)

- `apps/api/app/imagery/pgstac.py` — local/air-gapped catalog, `NotImplementedError` stub only.
- Change detection picks a single best-covering Sentinel-2 scene per date; AOIs spanning multiple MGRS tiles fail clearly rather than mosaicking (`TODO(v2)` in `change_detection_pipeline.py`).
- Placeholder detection tiles date B's true-color imagery into a small fixed grid (≤9 chips) rather than running on the full scene or targeting the change mask specifically — it demonstrates the pipeline end-to-end, not production-grade recall.
- Least-privilege DB roles are in place for the app itself (`vantage_migrate` owns schema DDL, `vantage_app` is DML-only at runtime — see `infra/db-init/01-roles.sql`); `pypgstac migrate` alone still runs as the bootstrap superuser (documented exception, see that file's comments — pypgstac's own role grants fail under a lower-privilege role).
- The tiler and inference services have no auth of their own — reachable only from other compose services, not exposed publicly.
- Packaged-app distribution (Tauri desktop launcher, offline installers) is v1.3 — see `INSTALL.md`, `docs/AIRGAP.md`, and `PACKAGE_REPORT.md` for what's genuinely built and verified there vs. environment-blocked in this repo's own dev history.
