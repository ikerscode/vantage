# COMPLIANCE.md (v1 stub)

This is a stub restating VANTAGE's hard invariants and current licensing posture for reviewers. It is **not** a legal opinion, and formal legal/compliance sign-off is pending — treat everything below as engineering-level self-attestation, not clearance.

## Analysis only — not a weapons system

VANTAGE reports **what is present** and **what changed** in overhead imagery. It does not, and must not, build or stub:

- Targeting, fire-control, or firing-solution logic
- Strike planning or weaponeering
- Sensor-to-shooter / kill-chain automation of any kind

This is a hard invariant, not a v1-vs-v2 scoping question — it never becomes in scope. Anyone extending this codebase should treat code review against this boundary (the ITAR/USML analysis-vs-targeting line) as a first-class check, not an afterthought.

`services/inference` exposes two selectable detector backends (`MODEL_BACKEND` env var). The default, `torchvision_fasterrcnn`, classifies generic COCO categories (people, vehicles, etc. — whatever a stock pretrained model recognizes) purely to demonstrate the detection pipeline's plumbing (chip extraction → inference call → geo-referenced bounding box → persisted `Detection` row); it is not tuned for, and makes no claim of being fit for, any operational identification or classification task. The opt-in `torchvision_fasterrcnn_vessel` (BRIEF v1.8) is fine-tuned on real, licensed Sentinel-2 vessel annotations and reports genuine (if imperfect) detection accuracy — see `VESSEL_DETECTION_REPORT.md` for the honest precision/recall numbers and failure modes. Neither is, or claims to be, anything beyond point/box detection of vessel presence and location — see "Analysis only" above.

## Self-hostable / air-gappable

No component in the core request path has a hard runtime dependency on external SaaS:

- Imagery: repointable via `IMAGERY_SOURCE`/`STAC_API_URL` (see `README.md`'s air-gap table); the only bundled v1 source hits the public Earth Search API, but the `ImagerySource` interface (`apps/api/app/imagery/base.py`) is the seam a local/air-gapped catalog implementation plugs into.
- Object store: any S3-compatible endpoint via env vars.
- Tiling: `services/tiler` is a self-hosted process, not a hosted tile API.
- Auth: the v1 JWT stub verifies real signatures/expiry; production self-hosts against Keycloak, not a third-party IdP (Clerk/Auth0 are explicitly out of bounds — see `CLAUDE.md`).
- Inference: `services/inference`'s model weights are baked into the image at *build* time specifically so the running container needs no runtime internet access.

## Licensing posture

- **Object detector**: `torchvision.models.detection.fasterrcnn_resnet50_fpn`, BSD-3-licensed, for both selectable backends above. **Ultralytics YOLO (AGPL-3.0) is explicitly not used anywhere in this codebase** — AGPL's copyleft terms are incompatible with a proprietary product, per `CLAUDE.md`'s locked constraints. Re-confirmed during BRIEF v1.8's dataset research: a YOLOv8 model trained on the same vessel dataset used below was found and correctly ruled out for this reason — the license restriction was on that model, not on the underlying dataset, which remained usable.
- **Training data**: no overhead-imagery dataset is bundled for the default backend. The opt-in vessel backend's training data (Zenodo 15019034, CC BY 4.0 — see `VESSEL_DETECTION_REPORT.md`) is the one deliberate exception, license-researched and documented, not baked in casually — acceptable specifically because this is a portfolio piece rather than a commercial product (non-commercial-friendly licensing is fine here; it would need reassessment before any commercial redistribution). The original xView dataset (CC BY-NC-SA 4.0) remains unused — resolution-mismatched for most classes at Sentinel-2's ~10m GSD.
- **Everything else**: FastAPI, SQLAlchemy, PostGIS, TiTiler/rio-tiler, MapLibre GL, deck.gl, Zustand, TanStack Query — all permissively licensed (MIT/BSD/Apache-2.0-family), consistent with a self-hostable, non-copyleft-encumbered product.

## Status

v1 scaffold. No formal legal, export-control, or compliance review has been performed on this codebase. Do not represent it as cleared for any operational use pending that review.
