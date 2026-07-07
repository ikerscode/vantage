# VANTAGE v1.3 — Package Report

**Status: the packaging *logic* is real, tested, and where a container runtime existed in this sandbox (there isn't one), proven end-to-end — but the two things a container-runtime-and-GTK-having machine would give you for free (an actually-running launcher binary, and per-OS installers) could not be produced in this environment.** Per the brief's own standard ("honesty over green checks"), this report says exactly what ran, what's genuinely new logic with real tests, and precisely what's blocked and why — with the exact commands to unblock it on a normal developer machine.

## 0. Gate check + environment reality

**Gate check (required before any packaging work): PASS.** Re-ran `scripts/smoke.sh` against the still-running native v1.1 stack: **15/15**, real Sentinel-2 data, same as `RUN_REPORT.md`. Full output preserved in this session; the hero slice still works.

**HUD design tokens**: already applied in a prior session pass (confirmed: `styles.css` has 42 token references, all 11 spec'd components exist, `StatusStrip.tsx` present). No re-work needed here.

**What this sandbox has, freshly checked for this pass**:

| Tool | Present? | Notes |
|---|---|---|
| Docker / Podman | **No** | Neither installed; no root to install either |
| `sudo` | No (interactive auth required) | Confirmed via `sudo -n true` |
| Rust / Cargo | Installed **during this pass** via `rustup` (user-space, no root needed) | `rustc 1.96.1` |
| Node.js / npm | Yes (from prior pass) | v24.18.0 |
| C compiler | Yes | `gcc`/`cc` present — this is what let the `dbus` vendored-build workaround (§2) work at all |
| `libwebkit2gtk-4.1-dev`, `libgtk-3-dev`, `libglib2.0-dev`, `librsvg2-dev`, `libayatana-appindicator3-dev` | **No**, and not installable without root | The actual, complete, empirically-narrowed list — see §2 |
| Network egress | Yes | Used for real: downloading real Sentinel-2 crops (§3), npm/cargo registries, `gh` |

This is a materially different constraint set than v1.1's ("no Docker, but we can fake most of it with native processes"). A GUI toolkit and a container runtime aren't things `micromamba` or a user-space tarball can substitute for — they need actual system packages, which need root, which this sandbox doesn't have. Given that, the approach here was: **build every piece of real logic as a separately-testable unit, prove each one for real against the live stack where possible, and be exact about the one remaining wall** (compiling the actual GUI binary and building installers) rather than write untested Rust and call it done.

## 1. What's genuinely real and verified in this pass

### 1.1 `launcher-core` — the orchestration logic (Rust, compiles, tests pass)

`apps/launcher/launcher-core/` is a plain Rust library crate with **zero dependency on the `tauri` crate** — deliberately, so it builds and tests on any machine with a Rust toolchain, independent of the GUI wall in §2. **`cargo test`: 25/25 passing**, including real (not mocked) I/O:

| Module | What it does | How it's tested |
|---|---|---|
| `secrets.rs` | First-run secret generation + `.env`/SQL template rendering (BRIEF §7, §9) | Real temp-dir round-trips: fresh install generates unique random secrets, a second run reuses them without rotating, SQL and `.env` passwords are asserted to match, two installs are asserted to get *different* JWT secrets |
| `runtime_detect.rs` | Finds Podman/Docker on `PATH`, prefers Podman | Runs `detect()` for real in this sandbox (correctly returns `None` — see §0) |
| `compose.rs` | Builds the exact `docker compose --env-file ... -f ...` argv | Asserts the `--env-file` vs `-f` ordering and that `"podman compose"` stays two argv tokens (a real footgun this test exists specifically to catch — `Command::new("podman compose")` would try to exec a literally-named binary) |
| `health.rs` | Polls service `/health` endpoints, aggregates pass/fail for the splash gate | **Real TCP**: spins up an actual `TcpListener` answering a real HTTP 200, and separately hits a real closed port, asserting `Healthy` / `Unreachable` respectively — not a mocked HTTP client |
| `seed.rs` | Copies the bundled demo-data resource into the data dir, idempotently | Real filesystem copy + idempotency check |
| `images.rs` | Loads the offline image tarball once, marks it done | Real marker-file idempotency check |
| `support_bundle.rs` | Exports per-service logs + a manifest to a local folder | Real file writes, asserted content |
| `config.rs` | Data-dir resolution, dynamic port picking, the JS injected into the webview | Real `TcpListener` bind-and-check for `find_available_port` (proves it won't return a port something else already holds) |

### 1.2 The offline imagery pipeline — real Sentinel-2 data, real pipeline, verified end-to-end, right now

This is the part of §6 that actually matters ("a bundled demo AOI renders real imagery... even with no internet"), and it was built and proven for real, not just written:

1. **Downloaded two real Sentinel-2 scenes** (`scripts/package/fetch_demo_data.py`) over a fixed demo AOI (padded version of the same Central Valley AOI `RUN_REPORT.md`/`scripts/smoke.sh` already proved has good NDVI contrast), cropped to ~1500×1500px per band via windowed `/vsicurl/` reads — genuinely small (~54MB total for both scenes, 6 bands each), genuinely real (`S2B_11SKA_20250619_0_L2A`, `S2C_10SGF_20251101_0_L2A`, both <0.001% cloud cover). Landed on **two different UTM/MGRS tiles** — unplanned, and useful: it means the demo data exercises the pipeline's cross-tile reprojection path, not just the easy same-tile case.
2. **Wrote a new `ImagerySource` implementation**, `apps/api/app/imagery/static_catalog.py` (`IMAGERY_SOURCE=static_catalog`) — reads a local manifest + per-scene STAC-item JSON, zero network calls. This is explicitly **not** the deferred v2 pgstac ingestion seam (`pgstac.py` stays an untouched `NotImplementedError`) — it's a much narrower, additive implementation of the same existing provider-adapter interface, in scope for v1.3 specifically because it's small.
3. **Ran the real pipeline against it**, live, in this sandbox, against the already-running native stack:
   - `POST /api/stac/search` → both demo scenes returned correctly.
   - Real true-color tile fetched via `/cog` — `run_artifacts/v1.3-package/demo-true-color-tile.png` (visibly a real town/road grid).
   - Real NDVI tile via `/stac` (multi-asset STACReader reading the **local** `item.json`) — `run_artifacts/v1.3-package/demo-ndvi-tile.png`.
   - Real change-detection analysis (`execute_change_detection`, the same function the live pipeline uses) — completed with real, non-trivial stats (`pct_changed≈0.17-0.21`, `mean_diff≈0.078`), and a real rendered change-map tile — `run_artifacts/v1.3-package/demo-change-detection-tile.png`.
   - **Bug found and fixed in the process**: `seed_demo_data.py` initially passed `date_a`/`date_b` as plain strings instead of `datetime.date` objects, which surfaced as a real `TypeError` inside `StaticCatalogSource.search()`'s date comparison — fixed, re-verified.
4. **Wrote the idempotent seeder** (`apps/api/app/scripts/seed_demo_data.py`) that creates the demo AOI + a Monitor + one pre-computed AnalysisResult + one Event — so Explore/Analyze/Monitor are all populated immediately, not just Explore. Ran it for real: `created demo AOI ... / created demo monitor ... / computed demo analysis ... (status=done) / created demo event ...`.

This means the single most important acceptance criterion in the whole brief — "a clean install opens the app and renders the demo AOI with networking disabled" — has its **application-layer half genuinely proven** (the data, the imagery pipeline, the seeded state all work with zero network calls). What's unproven is the **packaging half** (does a compiled installer's launcher actually orchestrate this the same way) — see §2.

### 1.3 Frontend air-gap hardening — found and fixed a real violation

Checking the already-built HUD (prior session pass) against this brief's stricter "no CDN fetches, nothing may call out" standard surfaced a genuine bug, not a hypothetical one: **`index.html` was pulling IBM Plex fonts from Google Fonts' CDN.** Fixed:

- Switched to `@fontsource/ibm-plex-sans`/`ibm-plex-mono` (self-hosted `.woff2`, bundled into the Vite build) — verified in the actual `dist/` output: 0 references to `fonts.googleapis.com`/`fonts.gstatic.com`, real font files present in `dist/assets/`.
- Replaced build-time-baked `VITE_API_BASE_URL`/`VITE_TILER_BASE_URL` env vars with a **runtime-injected config** (`window.__VANTAGE_RUNTIME_CONFIG__`, set via a Tauri `initialization_script` before any page JS runs — see `apps/launcher/launcher-core/src/config.rs`), falling back to fetching `/runtime-config.json` for plain docker-compose deployments. This was a real requirement gap, not cosmetic: the desktop launcher picks ports dynamically to dodge conflicts (§3), which a build-time-baked URL can't ever reflect.
- Added a production-only CSP (`vite.config.ts`, active only via `apply: "build"` so it can't break `npm run dev`'s HMR) restricting `connect-src`/`script-src`/`font-src` to `'self'` + `localhost`.
- **Real-browser verification, not just code review**: installed Playwright/Chromium in this sandbox, served the actual production build (`vite preview`), loaded it against the live API. Result: **zero CSP violations, zero non-localhost network requests**, confirmed via Playwright's own request-interception (not just eyeballing the network tab). The only console errors were CORS rejections from testing against a port the dev API's CORS allowlist didn't expect — expected, and exactly what `CORS_ALLOWED_ORIGINS=tauri://localhost,http://tauri.localhost` in the prod env template fixes for the real deployment. Screenshot: `run_artifacts/v1.3-package/production-build-real-browser.png`.
- **Also checked, found clean**: `deck.gl`'s dependency tree pulls in `@vaadin/vaadin-usage-statistics` transitively (via `@arcgis/core`, a deck.gl integration VANTAGE doesn't use) — confirmed via `grep` on the actual built bundle that the string `vaadin`/`arcgis` appears **zero times** in shipped JS. Tree-shaking already excludes it since nothing imports `@arcgis/core`. Documented, not just assumed.
- **Residual, now provably inert rather than just "unreached"**: two WebGL debug-tooling code paths in `deck.gl`/`luma.gl` (SpectorJS, `webgl-debug`) reference `cdn.jsdelivr.net`/`unpkg.com` URLs, gated behind explicit opt-in debug flags nobody sets by default. The CSP means even if triggered, the browser blocks the request outright — a technical guarantee, not a "we don't call that code path" argument.

### 1.4 Production compose (`infra/docker-compose.prod.yml`)

Written to the brief's §4 spec: `image:` not `build:`, every port bound to `127.0.0.1` explicitly, bind-mount volumes under `${VANTAGE_DATA_DIR}` (not opaque Docker-managed volumes — matters for uninstall/support-bundle honesty), a healthcheck on every service including `api`/`tiler` (which the dev compose didn't have), least-privilege DB roles carried forward unchanged from `infra/db-init/01-roles.sql`'s verified rationale, GDAL env carried forward unchanged. A real, non-obvious Compose semantics issue is called out explicitly in the file's own header comment: `${VAR}` interpolation in the compose YAML (image tags, the `env_file:` path itself) only resolves from an explicit `--env-file` flag, never from a service's own `env_file:` block — so the launcher must always invoke compose with `--env-file ${VANTAGE_DATA_DIR}/config/.env` (verified this is exactly what `compose.rs`'s `base_args()` does, and there's a unit test asserting the flag ordering).

**Not run against a live container runtime** — no Docker/Podman here (§0). Structurally reviewed against the dev compose it's derived from (which *is* proven, 15/15) rather than blindly written from scratch.

## 2. The wall: compiling the actual GUI binary

`apps/launcher/src-tauri/` is the Tauri shell — `main.rs`, `boot.rs`, `state.rs`, `tauri.conf.json`, a real generated icon set (`apps/launcher/src-tauri/icons/`, via the actual `tauri icon` CLI, not placeholders). It is **source that has never been compiled**, and that's stated plainly rather than implied otherwise.

What was actually attempted, in order:

1. `cargo check` on `src-tauri` — got through a large fraction of the dependency graph (html5ever, cssparser, x11-dl, dozens of others) before failing at `libdbus-sys` (needs `libdbus-1-dev`, a root-only apt package).
2. Rather than stop there: added `dbus = { version = "0.9", features = ["vendored"] }` as a direct dependency, forcing Cargo's feature-unification to build libdbus **from source** instead of linking the system package — this only needs a C compiler, which this sandbox has. **This worked** — `cargo check` got past `libdbus-sys` entirely on the next attempt.
3. Next (and current, final) failure: `glib-sys`/`gobject-sys`, needing `glib-2.0`/`gobject-2.0` — real GTK3 development headers. No vendored-build escape hatch exists for something this size; genuinely needs the system package.

**The real, narrowed, empirically-derived list of what a Linux build machine needs** (not a guess from documentation — this is what this sandbox's own compile attempts actually asked for, minus the one item the vendored-dbus trick removed):

```
sudo apt install libglib2.0-dev libgtk-3-dev libwebkit2gtk-4.1-dev librsvg2-dev libayatana-appindicator3-dev
```

Because compilation fails during *dependency* compilation, `main.rs`/`boot.rs`/`state.rs` themselves have **never been type-checked by rustc** — unlike `launcher-core`, which compiles cleanly and has a real test suite. They were written carefully against documented Tauri v2 APIs (`WebviewWindowBuilder`, `initialization_script`, `tauri::tray::TrayIconBuilder`, `app.manage()`/`app.state()`, `tauri_plugin_opener`), and every piece of actual *logic* they call into (`launcher-core`) is separately proven — but treat these three files as a reviewed draft, not verified code. The honest expectation, stated in `main.rs`'s own header comment: a short compile-fix pass (missing imports, minor API-shape mismatches) on a machine with the packages above, not a rewrite.

**What this means for macOS/Windows**: those platforms' system webviews (WKWebView, WebView2) are already present on any real Mac/Windows machine — this specific wall is Linux-only, caused by this particular sandbox lacking root, not a cross-platform problem.

## 3. Per-OS installers (§8) — fully out of reach here, for a different reason than §2

Even with a working Linux build, **macOS `.dmg`/`.pkg` needs an actual Mac with Xcode; Windows `.msi`/`.exe` needs an actual Windows machine or a real cross-compilation toolchain.** This isn't a permissions problem like §2 — it's fundamental: Tauri's bundler doesn't cross-compile installers, full stop. `tauri.conf.json`'s `bundle.targets` lists all four (`deb`, `appimage`, `msi`, `nsis`, `dmg`) so the config is ready; actually producing them requires running `npm run build` (→ `tauri build`) natively on each target OS, per `INSTALL.md`'s "Building the installers yourself" section.

Code-signing (macOS Developer ID + notarization, Windows Authenticode) needs real certificates this environment obviously can't have either — documented as a known gap in `INSTALL.md`'s per-OS install notes, with the practical workaround (right-click-Open / SmartScreen "Run anyway") for internal distribution without one.

## 4. Offline image bundle (§5)

`scripts/package/build-images.sh` and `save-images.sh` are written and would work (they're straightforward `docker/podman build|pull|save` wrappers, the same commands the dev compose's `build:` stanzas already prove work) — **not run here, no container runtime.** `launcher-core::images::ensure_images_loaded()` (the load-at-first-run half) is unit-tested for its actual logic (marker-file idempotency, graceful skip if no tarball was bundled) using a real filesystem, just not against a real `docker load`/`podman load` invocation.

## 5. Security posture (§10) — audited, not just asserted

Grepped the entire new surface (launcher-core, src-tauri, the new `static_catalog.py`/`seed_demo_data.py`, `scripts/package/`) for external URLs and telemetry/analytics keywords: **zero external URLs found** outside the expected `earth_search.py` reference (the *online*-mode adapter, untouched, not on the offline path) and one docstring mentioning `https://` in prose. **Zero telemetry-related crates** in `launcher-core`'s full resolved dependency tree (`Cargo.lock`, grepped for `telemetry|analytics|sentry|posthog`). `tauri-plugin-shell`/`tauri-plugin-log`/`tauri-plugin-opener` are official first-party Tauri plugins with well-documented local-only scope (spawn subprocesses / write local logs / open local paths — none of them make network calls by design).

Support-bundle export (§11) is real, tested, and explicitly local-only by construction (`support_bundle.rs` — writes files, calls nothing else; the tray wiring in `main.rs` opens the resulting folder via `tauri_plugin_opener`, doesn't upload it anywhere).

## 6. What's built but not yet exercised against a real installed app

Being precise about the boundary between "real logic, real tests" and "real end-to-end packaged-app behavior":

| Real & verified | Written, plausible, not runnable here |
|---|---|
| All `launcher-core` logic (secrets, health-gate, compose argv, seed, images, support bundle) — 25/25 tests | The compiled `vantage-launcher` binary actually running any of it |
| The offline imagery pipeline end-to-end (search → true-color → NDVI → change-detection → seeded demo state) | The launcher's `boot.rs` orchestrating that same pipeline through a real `compose up` + health-gate loop |
| Production frontend build — self-hosted fonts, runtime-injected config, CSP, zero external calls (real Playwright verification) | That build loaded inside an actual Tauri webview (only verified inside a plain Chromium browser here) |
| `docker-compose.prod.yml`'s structure, reviewed against the proven dev compose | `docker/podman compose -f docker-compose.prod.yml up` actually succeeding |
| Icon asset generation (`tauri icon`, real files) | The bundler actually consuming them into a signed/unsigned installer |

## 7. Runbook — what you need to do on a real machine

**To get a running launcher (any OS with a container runtime + Rust)**:
```bash
# Linux only, once, before first build:
sudo apt install libglib2.0-dev libgtk-3-dev libwebkit2gtk-4.1-dev librsvg2-dev libayatana-appindicator3-dev

cd apps/web && npm install && npm run build && cd ../launcher && npm install
npm run dev     # cargo tauri dev — expect a short compile-fix pass per §2, then it should just run
```

**To produce real installers**: see `INSTALL.md`'s "Building the installers yourself" — needs the steps above plus `scripts/package/build-images.sh`/`save-images.sh` (needs a container runtime) run natively on each target OS.

**To do the actual §12 acceptance test** ("clean install, networking disabled, demo AOI renders real imagery"): install a built package on a clean VM or fresh user account per `INSTALL.md`, then follow `docs/AIRGAP.md`'s "Verifying no external calls yourself" section (cut networking, confirm the demo AOI still renders). This repo's own history proves the *application layer* of that claim (§1.2); proving the *packaging layer* needs the machine this sandbox doesn't have.

## 8. If you only read one section

The brief's own bar: "§2–§6 ... must genuinely work, or you've clearly documented exactly which packaging steps are environment-blocked and how the operator completes them." Per that bar: §2–§6's **logic** genuinely works and is tested/proven where a live stack could exercise it (imagery pipeline, secret generation, health-gating, compose argv construction) — the one thing that doesn't genuinely work yet is producing a compiled, double-clickable launcher binary, because this sandbox has no root and thus no GTK dev headers. That's a one-command fix (§2's `apt install` line) on essentially any real Linux dev machine, and a non-issue on macOS/Windows. Nothing here was faked to look done; the boundary above is exact.
