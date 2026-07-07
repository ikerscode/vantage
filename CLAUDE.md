# CLAUDE.md — VANTAGE standing context

This file is the always-on architectural context for this codebase — the hard invariants and conventions that govern every change, regardless of which brief is currently in flight. It is referenced throughout the codebase (`COMPLIANCE.md`, code comments in `apps/api`, `apps/web`, `services/*`) as the authoritative source for these constraints.

**Reconciliation note (BRIEF v1.5)**: this file did not exist anywhere in the repository or filesystem before this pass, despite being cited by name across dozens of commits and comments — confirmed via `find` across the whole filesystem. It has been reconstructed here from the invariants that have in fact been consistently enforced throughout this project's history (see `RECONCILIATION_REPORT.md` for the full accounting). Treat this reconstruction as faithful to established practice, not as new policy.

## 1. Analysis only — not a weapons system (hard invariant, never in scope)

VANTAGE reports **what is present** and **what changed** in overhead imagery. It does not, and must not, build or stub:

- Targeting, fire-control, or firing-solution logic
- Strike planning or weaponeering
- Sensor-to-shooter / kill-chain automation of any kind

This is not a v1-vs-v2 scoping question — it never becomes in scope, at any version. Code review against this boundary (the ITAR/USML analysis-vs-targeting line) is a first-class check on every change, not an afterthought. See `COMPLIANCE.md` for the fuller restatement and current licensing/status posture.

## 2. Self-hostable / air-gappable (no hard external SaaS dependency in the core path)

No component in the core request path may have a hard runtime dependency on external SaaS:

- **Imagery**: repointable via `IMAGERY_SOURCE`/`STAC_API_URL`. The provider-adapter pattern (`apps/api/app/imagery/base.py`'s `ImagerySource` interface) is the seam — `EarthSearchSource` (public Earth Search, v1 default), `StaticCatalogSource` (bundled offline demo scenes), and `PgstacSource` (local/air-gapped catalog, deliberately `NotImplementedError` until its ingestion pipeline exists — v2) are the concrete implementations. New imagery backends are new adapters behind this interface, never a special-cased branch in application code.
- **Object store**: any S3-compatible endpoint via env vars (MinIO by default).
- **Tiling**: `services/tiler` is a self-hosted process, not a hosted tile API — and **tiles are never pre-rendered**; every tile is computed on request from the source COG/STAC asset. No pixel pyramid is persisted anywhere.
- **Auth**: the JWT stub verifies real signatures/expiry; production self-hosts against Keycloak. Third-party identity SaaS (Clerk, Auth0, etc.) is explicitly out of bounds — self-hosted only.
- **Inference**: `services/inference`'s model weights are baked into the image at *build* time specifically so the running container needs no runtime internet access.

## 3. Honest seams — never fake a capability

Where something is deferred, unimplemented, or a placeholder, it must say so in a way that's mechanically discoverable, not just in prose:

- `TODO(v2)` / `PLACEHOLDER(v1)` markers are grep-able and current — if you finish one, remove the marker in the same change.
- A stub that would silently return plausible-looking fake data is worse than one that raises `NotImplementedError` loudly (see `PgstacSource`).
- Verification claims (a debrief saying "X is fixed/done") must be traceable to a real commit, a real test run, or a real command's output — not asserted from memory of a prior session. (This is the specific failure BRIEF v1.5 exists to correct — see `RECONCILIATION_REPORT.md`.)

## 4. Locked technology choices

| Layer | Choice | Why it's locked |
|---|---|---|
| Object detector | `torchvision.models.detection.fasterrcnn_resnet50_fpn` (BSD-3), COCO-pretrained | **Ultralytics YOLO (AGPL-3.0) must never be used anywhere in this codebase** — AGPL's copyleft terms are incompatible with a proprietary product. This is the single most-repeated licensing constraint in this codebase's history; treat any dependency change touching object detection as a licensing review, not just a technical one. |
| Backend | FastAPI, SQLAlchemy 2 + GeoAlchemy2, Alembic, pydantic-settings | — |
| Data | PostgreSQL + PostGIS + pgstac, SRID 4326 | — |
| Async jobs | Celery + Redis (+ celery-beat) | — |
| Tiling | TiTiler / rio-tiler | Dynamic tiling only — see §2's no-pre-rendering rule. |
| Frontend | React 18 + TypeScript + Vite, MapLibre GL + deck.gl (vectors/drawing), Zustand, TanStack Query | No hosted basemap tiles (Mapbox/MapTiler/OSM demo servers) — see §2; the map style is an inline dark void, not a third-party style API. |
| Training data | No bundled overhead-imagery dataset (xView or similar) | Frequently non-commercial-licensed; selecting one is a deliberate, deferred, licensing-sensitive decision, never baked in casually. |

## 5. Mission-console UX, not a SaaS dashboard

The UI floats over a full-bleed map. Observation, not engagement — no crosshairs, no lock-on iconography, no red target boxes; one accent color for chrome/selection, detections rendered neutrally (opacity scaled by confidence, not color-coded as a threat level).

## 6. Where this file is enforced

- `COMPLIANCE.md` — the reviewer-facing restatement of §1 and licensing posture.
- `.github/workflows/ci.yml`'s `security-scan` job — the weapons-boundary grep (§1) runs as an automated merge gate, not just a manual check (see `RECONCILIATION_REPORT.md`, `CI_REPORT.md`).
- Every `RUN_REPORT.md` / `PACKAGE_REPORT.md` / `SECURITY_FIXES_REPORT.md` / `RECONCILIATION_REPORT.md` — the "prove it, don't assert it" standard in §3 is what those documents exist to satisfy.
