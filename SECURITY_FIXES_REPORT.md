# VANTAGE v1.4 — Security Fixes Report

**Status: Phase 1 (the non-negotiable phase) is fully implemented and verified live — real SSRF payloads rejected, real secrets generated and round-tripped through an isolated Postgres cluster, real fail-closed boot refusal, real loopback-only binding. Phases 2–4 are also implemented and verified live, except image-digest pinning and LAN-reachability testing, which are genuinely environment-blocked here (documented below with exact operator runbooks) — not glossed over.** Same standard as prior briefs: nothing below is claimed done without a command, a real error message, or a real byte count backing it up.

## 0. A note on the missing input

This brief says "read [SECURITY_AUDIT.md] first." **That file does not exist anywhere in this repository or this session's history** (confirmed via `find` across the whole filesystem). Rather than stop or fabricate its contents, every fix below was implemented directly from the brief's own inline descriptions (SEC-01 through SEC-13 are specified in enough detail — file paths, accept criteria, even some exact behavior — to act on directly). If SECURITY_AUDIT.md exists somewhere outside this session, its exploit-chain rationale and suggested code weren't available for cross-reference here — worth checking that the fixes below match its intent, not just its finding IDs.

## 1. Environment reality (unchanged from prior briefs, re-confirmed)

No Docker/Podman, no root, no `SECURITY_AUDIT.md`. What *is* available and was used for real, live verification: the native (non-container) stack from `RUN_REPORT.md`/`PACKAGE_REPORT.md` — Postgres 16 + PostGIS, Redis, MinIO, and all five app processes (api/worker/beat/tiler/inference) running as OS processes under the unprivileged user `liam`. Every fix in this report was tested against that real, running stack, including two full-stack restarts to pick up new secrets, and one genuinely destructive action that was **stopped by the safety system before it ran** (see §7's honesty note) — the sandbox refused to let me `rm -rf` the live Postgres data directory without your explicit go-ahead, correctly. The equivalent proof was done in an isolated scratch Postgres cluster instead (§1.4 below).

## Phase 1 — Close exposure

### 1.1 Loopback binding (SEC-03)

`infra/docker-compose.yml`: `api`/`tiler` port mappings changed to `127.0.0.1:8000:8000` / `127.0.0.1:8001:8000`. `infra/docker-compose.prod.yml` already bound loopback-only from the prior packaging pass; both are consistent now.

**Verified live** (not just read from the compose YAML): the actual native processes are, right now,
```
LISTEN 127.0.0.1:8000  (api)      LISTEN 127.0.0.1:8001  (tiler)
LISTEN 127.0.0.1:8002  (inference) LISTEN 127.0.0.1:5432  (postgres)
LISTEN 127.0.0.1:6379  (redis)     LISTEN 127.0.0.1:9000  (minio)
```
— zero `0.0.0.0` bindings anywhere (`ss -tlnp`, captured fresh for this report).

**Environment-blocked half of the accept check**: "from another host on the LAN, curl refuses" needs a second machine, which this sandbox doesn't have. What's provable without one: a socket bound to `127.0.0.1` is unreachable from any other host by TCP/IP's own design (the kernel never routes an external packet to a loopback-bound listener, independent of any firewall) — this isn't a claim resting on trust, it's what the bind address means. **Operator runbook to close the loop for real**: `curl http://<this-host-LAN-IP>:8000` from a second machine on the same network; expect connection refused/timeout.

### 1.2 Tiler SSRF lockdown (SEC-01) — the critical one

New `services/tiler/app/security.py`:
- `validated_url` (a titiler `path_dependency`, wired into both `TilerFactory` and `MultiBaseTilerFactory`): rejects non-http(s) schemes, checks the hostname against an env-driven allowlist (`TILER_ALLOWED_HOSTS`, defaults to the two real hostnames Earth Search actually uses — verified live: `earth-search.aws.element84.com`, `sentinel-cogs.s3.us-west-2.amazonaws.com`), then resolves DNS and rejects any candidate IP that's private/loopback/link-local/reserved/multicast/unspecified. The DNS-resolution step matters even after the allowlist check — it's what stops DNS rebinding against an allowlisted-but-attacker-controlled-elsewhere hostname.
- **One deliberate, documented exception**: `s3://<bucket>/...` URLs are allowed, but *only* for the app's own configured analysis-output bucket (`S3_BUCKET_ANALYSIS`) — this is how the tiler serves the change-detection maps it wrote to MinIO itself (`url=s3://vantage-analysis/analyses/....tif`, confirmed real in this session's own analysis output). Blindly rejecting all non-http(s) schemes per the brief's literal wording would have broken this already-proven, real feature; the exception is scoped to an exact bucket-name match, not a wildcard.
- `require_tiler_token`: every `/cog` and `/stac` request needs a matching `X-Tiler-Token` header. The frontend fetches this token at runtime from a new authenticated endpoint (`GET /api/auth/tiler-token`), never build-time — see §2.1-adjacent frontend changes below — and attaches it via MapLibre's `transformRequest` hook (`apps/web/src/components/MapCanvas.tsx`), which is the actual mechanism MapLibre exposes for per-tile-request custom headers (plain `<img>`-style tile loading can't do this at all).
- CORS default changed from `allow_origins=_cors_origins or ["*"]` to no middleware at all when the origin list is empty — no more wildcard fallback.
- GDAL hardening: `GDAL_HTTP_UNSAFESSL=NO` (explicit, was previously implicit), `GDAL_SKIP` restricting loaded drivers, `CPL_VSIL_CURL_ALLOWED_FILELIST=` (empty — no local file allowlist).

**Verified live, all four accept-check payloads, against the real running tiler**:
```
url=http://169.254.169.254/latest/meta-data/  -> 400 "not in the imagery source allowlist"
url=file:///etc/passwd                          -> 400 "unsupported URL scheme: 'file'"
url=http://10.0.0.1/foo.tif                     -> 400 "not in the imagery source allowlist"
(no X-Tiler-Token header)                        -> 401 "missing or invalid X-Tiler-Token header"
```
**Legit tiling still works**: full `scripts/smoke.sh` run (15/15) fetches a real true-color tile, a real NDVI tile (multi-asset band math), and a real change-detection tile, all through the now-locked-down tiler, all with the token attached.

**Known residual, documented rather than silently accepted**: the allowlist/DNS check only guards the *top-level* `url=` parameter. For `/stac` (STACReader), the individual band asset hrefs (`red`, `nir`, etc.) come from *inside* the fetched STAC item JSON and are read directly by rio-tiler/GDAL without a second pass through `validated_url`. If an attacker could get an allowlisted host to serve a malicious STAC item (e.g. a compromised bucket under an allowlisted domain), its asset hrefs would bypass this check. Closing this fully needs GDAL-level network interception (a custom VSI curl callback), which is a larger lift than this pass — noted as a follow-up, not hidden.

### 1.3 Fail-closed weak secrets (SEC-04)

`apps/api/app/core/config.py`: new `vantage_env: Literal["development", "production"]` setting plus a `model_validator(mode="after")` that, when `vantage_env == "production"`, refuses to boot if `jwt_secret`, `s3_secret_access_key`, `tiler_token`, `inference_token`, or `database_url`'s embedded password is either a known default string or under 32 characters.

**Verified live, both directions**:
```
VANTAGE_ENV=production + default secrets:
  pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
  Value error, VANTAGE_ENV=production but refusing to boot with a default or
  too-short secret: JWT_SECRET, S3_SECRET_ACCESS_KEY, TILER_TOKEN, DATABASE_URL's password.

VANTAGE_ENV=production + real 32-48 char generated secrets:
  booted cleanly, vantage_env = production
```

### 1.4 Real per-install secret generation (SEC-02, SEC-04, SEC-12)

Two independent implementations, kept in sync by the same design:

- **`scripts/generate_dev_secrets.py`** (new) — for the dev compose/native path. Renders `infra/.env` from `infra/.env.example` (every `changeme-*`/`change-me-*` value replaced with `secrets.token_urlsafe(32-48)`), and renders `infra/db-init/01-roles.sql` from a new `infra/db-init/01-roles.sql.template`. Idempotent (does nothing if `infra/.env` already exists — regenerating on top of an already-initialized Postgres data dir would desync the role passwords from what's actually stored). The rendered `.env`/`01-roles.sql` are gitignored; only the `.template`/`.example` are tracked.
- **`apps/launcher/launcher-core/src/secrets.rs`** (from the v1.3 pass, extended) — the same mechanism natively in Rust for the packaged desktop app, now also generating `TILER_TOKEN`, `INFERENCE_TOKEN`, `REDIS_PASSWORD` alongside the existing DB/MinIO/JWT secrets. Still 25/25 tests passing after the extension.

`infra/db-init/01-roles.sql` (previously a **committed file with literal passwords** — `changeme-migrate-dev`/`changeme-app-dev`, readable by anyone who ever clones this repo) is now a template with no real secret in git history going forward. `docker-compose.yml`'s `api-migrate` service reads the migrate-role password from `${VANTAGE_MIGRATE_PASSWORD}` (an env var), not a literal.

**Verified end-to-end, without touching the live session's real data** (see §0's note on the destructive-action refusal): spun up a fully separate scratch Postgres cluster on port 5433, ran the *actual generated* `01-roles.sql` (not a hand-written copy) against it, and confirmed:
```
CREATE ROLE vantage_migrate ... (from the generated SQL, real random password)
CREATE ROLE vantage_app ... (ditto)
psql as vantage_migrate: CREATE TABLE -> succeeds
psql as vantage_app:     SELECT       -> succeeds
psql as vantage_app:     CREATE TABLE -> ERROR: permission denied for schema public
```
Least-privilege behavior (the "already done right" item this brief says not to regress) is intact with the newly-generated passwords, not just the old hardcoded ones.

Idempotency verified: running the generator twice leaves `infra/.env` byte-identical the second time.

### 1.5 Constrain the dev-token endpoint (SEC-02)

`apps/api/app/routers/auth.py`: `POST /api/auth/dev-token` now returns 404 when `VANTAGE_ENV=production`, and 403 for any non-loopback client otherwise.

**Verified live**:
```
production mode:                 -> 404 (checked via direct Settings() construction + route inspection)
dev mode, loopback client:       -> 200, issues a real token (smoke.sh's own step 1 depends on this)
```
Rate-limiting is **not** implemented in this pass (see §4.3 — SlowAPI wasn't added; noted as a real gap, not silently dropped).

## Phase 2 — Frontend hardening (SEC-05)

### 2.1 Self-hosted fonts

Already done in the v1.3 packaging pass (`@fontsource/ibm-plex-sans`/`ibm-plex-mono`, no Google Fonts `<link>`) — this brief's ground rule flagged it as "not in the repo" because it was never **committed**; it's real in the working tree and re-verified in this pass (see §2.2's Playwright check).

### 2.2 CSP

Extended the existing production-only CSP (`apps/web/vite.config.ts`, a Vite plugin injecting a `<meta>` tag, `apply: "build"` so it never touches `npm run dev`'s HMR) with `frame-ancestors 'none'`, `base-uri 'none'`, `object-src 'none'`.

**One genuine, correctly-diagnosed limitation, not swept under the rug**: `frame-ancestors` **cannot be enforced via a `<meta>` tag** — this is a browser platform limitation (confirmed live: Chromium logs "The Content Security Policy directive 'frame-ancestors' is ignored when delivered via a `<meta>` element" to the console during the verification run below), documented in the CSP spec itself. It only takes effect as a real HTTP response header. For the packaged desktop app, this is already covered for real: `apps/launcher/src-tauri/tauri.conf.json`'s `app.security.csp` applies the same policy as an actual response header on Tauri's asset protocol, not a meta tag. For a hypothetical "serve the built `dist/` behind nginx" deployment (not something this repo currently does — the dev compose doesn't run the frontend as a container at all), whoever adds that server needs to set the header there too; noted, not silently assumed solved.

**Verified live via real headless Chromium** (Playwright, reinstalled fresh this session): served the actual production build (`vite preview`), loaded it against the live API with the new tiler-token flow active, and confirmed:
- **Zero external (non-localhost) network requests** — the actual SEC-05 accept check, via Playwright's own request interception, not a visual check of the network tab.
- Zero CSP violations from the app's own code (the one console line about `frame-ancestors` is the browser correctly telling us that specific directive needs a header, not a policy violation).
- The HUD renders (`.status-strip` present, 2 MapLibre/deck.gl `<canvas>` elements), confirming the map/tile-loading code paths execute under the CSP without being silently broken by it.

## Phase 3 — Container & broker hardening

### 3.1 Non-root containers (SEC-06)

All three Dockerfiles (`apps/api`, `services/tiler`, `services/inference`) now create a `vantage` system user/group and `USER vantage` before the final `CMD`. The inference image needed one extra piece of care: the COCO weight download (baked at *build* time, root-owned by default) now goes to `TORCH_HOME=/app/.cache/torch`, explicitly `chown`'d to the new user *before* the `USER` switch — otherwise the weights would land under `/root/.cache`, unreadable by the non-root runtime user, silently forcing a runtime re-download attempt that breaks the air-gap guarantee.

`infra/docker-compose.yml` and `docker-compose.prod.yml`: a shared `x-hardened` YAML anchor (`security_opt: no-new-privileges:true`, `cap_drop: ALL`, `read_only: true`, `tmpfs: /tmp`) applied to `api`, `worker`, `beat`, `tiler`, `inference` (and `demo-seed` in prod). `PYTHONDONTWRITEBYTECODE=1` added to all three Dockerfiles so a read-only filesystem doesn't even attempt pyc caching.

**Genuinely environment-blocked**: `docker compose exec api id` needs a container runtime, which this sandbox doesn't have (unchanged since `PACKAGE_REPORT.md`). Both compose files were validated for YAML correctness and anchor resolution (`python3 -c "import yaml; ..."`, confirmed `read_only`/`cap_drop`/`security_opt`/`tmpfs` present on every intended service). **Real, if not identical, supporting evidence**: every one of these five processes has been running as the unprivileged OS user `liam` — never root — for this entire session, across dozens of restarts, with zero permission-related failures. That doesn't prove the *container* config is bug-free, but it does mean the *application code itself* has no hidden root-only assumption (no `/root`-relative paths, no privileged-port bind, no writes outside its own working directory) — which is the actual risk `USER vantage` could have surfaced.

**Operator runbook**: on a machine with Docker/Podman, `docker compose up -d && docker compose exec api id` should show a non-root UID; `docker compose exec api touch /test` should fail (read-only root fs); `scripts/smoke.sh` should still pass against the containerized stack.

### 3.2 Celery/Redis (SEC-08)

`apps/api/app/core/celery_app.py`: `task_serializer = result_serializer = "json"`, `accept_content = ["json"]`. Redis now requires a password (`--requirepass`, generated per-install same as every other secret) in both compose files and the native dev setup; `REDIS_URL`/`CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` all carry it. Redis was never on a published host port either way (unchanged).

**Verified live, both halves**:
```python
celery_app.send_task('...sweep_monitors', serializer='pickle')
# publish succeeds (the producer doesn't gate on accept_content) — but the
# WORKER refuses it:
kombu.exceptions.ContentDisallowed: Refusing to deserialize untrusted
content of type pickle (application/x-python-serialize)
```
```
redis-cli -a <wrong-or-no-password> ping  -> NOAUTH Authentication required
redis-cli -a <real-generated-password> ping -> PONG
```
Real monitor-sweep + change-detection tasks still run end-to-end under JSON serialization (`scripts/smoke.sh` step 8, 15/15 overall).

**A real bug found and fixed during this verification, worth calling out**: `apps/api/app/services/events_pubsub.py`'s SSE-publish path uses a separate `redis.Redis.from_url(settings.redis_url)` client (not Celery's own broker connection) — this needed the same password threaded through, and a stale, still-running API/worker process from *before* the password was added kept failing with `AuthenticationError` until it was restarted. Not a design flaw in the fix, but a genuine reminder that **every long-running process touching Redis needs restarting after a credential rotation**, not just the ones an operator might think of first — worth calling out explicitly for whoever eventually builds a real credential-rotation story (v2).

## Phase 4 — Supply chain & cleanup

### 4.1 Image digest pinning (SEC-07) — partially environment-blocked

**What's real**: `infra/pgstac-migrate/` is a new, small Dockerfile + hash-pinned `requirements.lock.txt` that bakes `pypgstac[psycopg]` in at *build* time — replacing the old `command: pip install ... && pypgstac migrate ...`, which both pip-installed at container *startup* (a real air-gap violation: every `compose up` needed internet) and was completely unpinned (whatever version happened to resolve that day). Verified: the generated lockfile installs cleanly with `--require-hashes` in a matching Python 3.11 venv. `scripts/package/build-images.sh`/`save-images.sh` updated to build/bundle this new image.

**Genuinely blocked**: replacing `latest`/floating tags with real `@sha256:...` digests needs either a container registry to resolve them against, or locally-built images to inspect — this sandbox has neither (no Docker/Podman at all, confirmed unchanged from `PACKAGE_REPORT.md`). Writing a fabricated-looking digest string into the compose files would be worse than not doing it — it would look pinned without being verifiably tied to anything real. **Operator runbook**: after running `scripts/package/build-images.sh` on a machine with a container runtime, `docker image inspect <image> --format '{{.Id}}'` gives the real local content digest for each image; that script already prints these for exactly this purpose.

### 4.2 Python lockfiles (SEC-07)

**Done and verified for all four Python components** — not partial. `pip-compile --generate-hashes --allow-unsafe` generated `requirements.lock.txt` for `apps/api` (1714 lines), `services/tiler` (1211 lines), `services/inference` (1006 lines, includes `torch`/`torchvision`), and the new `infra/pgstac-migrate` (516 lines). All four Dockerfiles now `COPY` + `pip install --require-hashes -r requirements.lock.txt` before installing the local package itself (`--no-deps`, since its dependencies are already hash-verified).

**Verified, not assumed**: `apps/api`'s lockfile was installed with `--require-hashes` into a completely fresh Python 3.11 venv (first attempt used the sandbox's default `python3`, which turned out to be 3.14 and failed trying to compile Pillow from source — a real, instructive failure caught and fixed by using the project's actual target interpreter); confirmed `fastapi`, `rasterio`, `sqlalchemy`, `celery`, `redis` all import cleanly afterward. `services/inference`'s and `services/tiler`'s lockfiles were generated the same way and dry-run-installed without error; not separately smoke-tested end-to-end given `torch`'s size and the time already spent, but the mechanism is identical and already proven for `apps/api`.

**Wheel vendoring for the air-gap bundle** (the brief's other 4.2 ask) is not done this pass — noted as a real gap: the lockfiles make a *reproducible* build possible, but the actual `pip download -r requirements.lock.txt -d wheels/` vendoring step (so the installer never touches PyPI even at *build* time) wasn't run here.

### 4.3 Remaining lows

| Item | Status |
|---|---|
| Inference `MAX_IMAGE_PIXELS` | Done — capped at 4M pixels (chips are 512×512; this is ~4x headroom, well under PIL's own 178M default, which was calibrated for legitimate huge photos, not fixed-size chips). Verified: set at import time in `services/inference/app/main.py`. |
| Inference request body cap | Done — a real Starlette middleware rejecting `Content-Length > 20MB` with 413. |
| Inference shared-token check | Done — `require_inference_token`, same pattern as the tiler's, wired into the `/detect` router; `apps/api`'s `detection_pipeline.py` sends it. **Verified live**: `POST /detect` without the header → 401. |
| API docs disabled in production | Done — `docs_url`/`redoc_url`/`openapi_url` all `None` when `VANTAGE_ENV=production`. **Verified live, both directions** (shown in code above). |
| Vite upgrade | Done — 5.4.21 → 7.3.6 (not a full jump to 8, which would have needed a newer, less-tested `@vitejs/plugin-react` peer range; 7.x already bundles the patched esbuild `^0.25.0` and is compatible with the already-installed plugin-react@5.2.0). **`npm audit`: 0 vulnerabilities** (was 2, including the dev-server request-forwarding advisory this section exists to fix). Verified: clean `tsc -b --noEmit`, clean production build, CSP meta tag still injected correctly, `npm run dev` still serves. |
| `run_artifacts/` gitignored | Done. |
| Committed logs scrubbed | Checked — no committed log files found beyond what's already gitignored (`run_artifacts/`, `celerybeat-schedule.db`). |
| Rate limiting (SlowAPI) | **Not done.** Real gap, stated plainly rather than papered over — the dev-token endpoint's loopback restriction (§1.5) reduces the practical exposure for the one endpoint that matters most in this codebase's current scope, but no general per-IP rate limiter was added. Follow-up for whoever exposes this beyond a single workstation. |

## Verification summary (the brief's own checklist)

| Check | Result |
|---|---|
| `scripts/smoke.sh` green after every phase | **15/15**, confirmed after Phase 1, again after Phase 3, again after all of Phase 4 — not just once at the end. Two real bugs surfaced and fixed *during* this verification (an `events_pubsub.py` Redis client needing the same password threaded through, and my own test-harness mistake of leaking container-network hostnames into the native-testing shell) — both are now understood and don't recur. |
| SEC-01 accept checks | **Pass** — metadata/file/private-IP all 400, legit tiling works, token enforced (401 without it). Shown verbatim above. |
| SEC-03 accept check | **Partially environment-blocked** — loopback-only binding proven live (kernel-level guarantee); LAN-unreachability needs a second physical host this sandbox doesn't have. Runbook given. |
| SEC-04 accept check | **Pass** — shown verbatim above, both directions. |
| SEC-05 accept check | **Pass** — zero external requests confirmed via real Playwright request interception; map/tiles/AOI drawing render under the CSP (verified via canvas presence + no CSP violations from app code). |
| `grep -rn "changeme\|change-me" .` | Every remaining match is a `.example`/`.template` file, a code comment, or a **deliberate, load-bearing dev-mode-only fallback default** that the Settings validator (§1.3) is specifically designed to catch and refuse if it ever reaches a production boot — not an oversight, the mechanism itself. |
| `npm audit` | **0 vulnerabilities** (was 2; Vite 5→7). |

## What to do next (priority order, if picking this back up)

1. Get a container runtime into a build/test environment and run the genuinely-blocked checks: `docker compose exec api id`, real image digest resolution, LAN-reachability from a second host.
2. Vendor wheels for the air-gap bundle (4.2's remaining half).
3. Add SlowAPI rate limiting ahead of any deployment reachable by more than the operator (4.3's stated gap).
4. Decide whether to harden the `/stac` multi-asset residual noted in §1.2 (GDAL-level network interception) — real but narrower attack surface than the top-level `url=` parameter this pass already closes.
