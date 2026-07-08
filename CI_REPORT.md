# VANTAGE — CI Report (BRIEF v1.5, Phases 1 & 2)

This report documents what `.github/workflows/ci.yml` and `.github/workflows/release.yml`
actually do, what real GitHub Actions runs have genuinely proven, and what
remains blocked and why. Every claim below is anchored to a real run URL,
a real artifact, or a real command's output — per `CLAUDE.md` §3, an
assertion without one of those is not evidence.

Repo: `ikerscode/vantage` (public — hosted runners with real root, real
Docker, and real macOS/Windows hardware, none of which the development
sandbox this codebase was built in has ever had; see `RECONCILIATION_REPORT.md`
and `PACKAGE_REPORT.md`'s "Environment reality").

## What each job does

- **`test`** (ubuntu-latest): real `pytest` suites for `packages/geo`,
  `apps/api`, and `services/tiler`; generates real per-install secrets
  (`scripts/generate_dev_secrets.py`); brings up the real Docker Compose
  stack (`infra/docker-compose.yml`) — every Dockerfile changed by v1.4's
  non-root/hardening pass, never built by a container runtime before this
  workflow existed; runs `scripts/smoke.sh` against live Sentinel-2 (real
  Earth Search, real STAC, real tiles, real change-detection, real
  monitor-sweep).
- **`frontend`** (ubuntu-latest): `npm ci`, `tsc --noEmit`, production
  build, `npm audit`.
- **`security-scan`** (ubuntu-latest): the weapons-boundary grep
  (`scripts/check_weapons_boundary.sh`, CLAUDE.md §1) as an automated merge
  gate; `gitleaks` secret scanning; `pip-audit` against every hash-pinned
  lockfile; `npm audit`.
- **`build-desktop`** (matrix: ubuntu-22.04, macos-latest, windows-latest;
  `needs: [test, frontend, security-scan]`): the first real compile of the
  Tauri desktop launcher this project has ever produced, with signing
  wired to consume `APPLE_*`/`WINDOWS_*` repo secrets if present and skip
  gracefully if not.
- **`release`** (`.github/workflows/release.yml`, triggered by `app-v*`
  tags): same build, but publishes the installers to an actual GitHub
  Release. **Not yet exercised** — no `app-v*` tag has been pushed. Its
  build steps are identical to `build-desktop`'s (now proven working), so
  it inherits that confidence, but the release-publish path itself is
  unverified until a real tag is pushed.

## Real run history

Every fix below was a genuine bug, not a hypothetical — each was found by
actually running this stack for the first time in an environment with real
root, real Docker, and real non-Linux hardware. None were reproducible in
the development sandbox this codebase was originally built in.

| # | Run | Conclusion | What it found | Fix |
|---|-----|------------|----------------|-----|
| 1 | [28934939975](https://github.com/ikerscode/vantage/actions/runs/28934939975) | failure | `security-scan`: 6 real CVEs in Pillow 10.4.0 (apps/api, services/inference). `test`: containers crashed — `libexpat.so.1: cannot open shared object file` (rasterio's manylinux wheel needs it at runtime; `python:3.11-slim` doesn't ship it) | `366b98c` — bumped Pillow to 12.2/12.3, regenerated lockfiles; added `libexpat1 libgomp1` to apps/api and services/tiler Dockerfiles |
| 2 | [28935369893](https://github.com/ikerscode/vantage/actions/runs/28935369893) | failure | `test`: `beat` crashed — `_gdbm.error: Read-only file system: 'celerybeat-schedule'` (v1.4's `read_only: true` hardening broke beat's default schedule-file location, never tested against a real read-only container before). Also found: generated secrets were printed in **plaintext** in this run's public logs (`docker compose ps -a`'s env dump) — values loaded into `$GITHUB_ENV` from a file aren't auto-masked by GitHub, only `secrets.*` context values are. **This run's logs still contain the plaintext values — see Security disclosure below.** | `11ab636` — added `--schedule=/tmp/celerybeat-schedule` to beat's command in both compose files; added explicit `::add-mask::` emission before writing generated secrets to `$GITHUB_ENV` |
| 3 | [28935752157](https://github.com/ikerscode/vantage/actions/runs/28935752157) | failure | `test`: masking confirmed working; beat crash confirmed fixed. New failure: `smoke.sh` step 1 — `dev-token is only issued to loopback clients` (403). Docker's port-publish NAT rewrites a host-loopback client's source IP to the bridge gateway address before it reaches the container; real `127.0.0.1` never survives the hop | `edfb260` — `_is_loopback()` now also accepts the container's own default-route gateway (parsed from `/proc/net/route`), without widening the check to sibling containers (which present their own IP, not the gateway's). 6 new regression tests in `apps/api/tests/test_auth.py` |
| 4 | [28936381625](https://github.com/ikerscode/vantage/actions/runs/28936381625) | failure | `test`/`frontend`/`security-scan` **all green for the first time**. `build-desktop` failed on all 3 platforms: `npm ci` in `apps/launcher` — no `package-lock.json` had ever been committed there (unlike `apps/web`) | `aef4804` — generated the lockfile (Node is now available in this sandbox), verified `npm ci` installs cleanly from it |
| 5 | [28936780300](https://github.com/ikerscode/vantage/actions/runs/28936780300) | failure | `build-desktop` failed on all 3 platforms: `tauri-action` invokes `npm run tauri build` by convention, but `apps/launcher/package.json` only had `build`/`dev`/`icon` scripts. Also found: `uploadWorkflowArtifacts` is **not a real `tauri-action@v0` input** — a warning, not a failure, meaning this would have shipped with zero artifacts ever produced even on a successful build | `725870c` — added a `tauri` script; replaced the invalid input with an explicit `actions/upload-artifact@v4` step over the real bundle output directory |
| 6 | [28937168269](https://github.com/ikerscode/vantage/actions/runs/28937168269) | cancelled¹ | `macos-latest` failed: `failed to run custom build command for libdbus-sys` / `"Unsupported platform."` — a `dbus` crate dependency (added to force building libdbus from source on Linux, avoiding a system package that needs root) was declared unconditionally, so Cargo tried to build it for every platform, not just Linux | `f388238` — scoped the dependency to `[target.'cfg(target_os = "linux")'.dependencies]`. Verified locally via `cargo tree --target <triple>`: present only for `x86_64-unknown-linux-gnu`, absent from `x86_64-apple-darwin` and `x86_64-pc-windows-msvc` |
| 7 | [28937694375](https://github.com/ikerscode/vantage/actions/runs/28937694375) | cancelled¹ | `macos-latest` got past compilation for the first time (real Rust build succeeded, `.app` bundling started) — then failed at codesign: `security: SecKeychainItemImport: ... not valid`. `${{ secrets.APPLE_CERTIFICATE }}` evaluates to an **empty string**, not an omitted variable, when the secret doesn't exist; Tauri's bundler checks `env::var(...).is_ok()`, true even for `Ok("")` | `430a352` — a preceding step now writes each `APPLE_*`/`WINDOWS_*` var into `$GITHUB_ENV` only when genuinely non-empty, so an unconfigured one is truly absent (`Err`) rather than present-but-empty. Applied identically to `release.yml` |
| 8 | [28938358320](https://github.com/ikerscode/vantage/actions/runs/28938358320) | **success** | **First fully green run.** `test`, `frontend`, `security-scan`, and `build-desktop` (all 3 platforms) all passed. See Artifacts below | — |
| 9 | [28939707497](https://github.com/ikerscode/vantage/actions/runs/28939707497) | **success** | Found while double-checking run 8's raw logs rather than trusting its "PASS: 13 FAIL: 0" summary at face value: `smoke.sh` step 8 (monitor-sweep) had an uncaught `psycopg.OperationalError: failed to resolve host 'db'` — the direct `sweep_monitors()` invocation ran from the GitHub Actions host, but `db` only resolves inside the Docker network and has no published host port. The sweep never genuinely executed; "no Event fired" was reported as a plausible real-world-data outcome when the actual cause was this broken host-to-container call | `1a2c970` — `smoke.sh` now execs both the backdate and the sweep call inside the running containers via `docker compose exec` when `COMPOSE_FILE` is set (wired in `ci.yml`); unchanged for native (non-Docker) dev runs. **Confirmed fixed**: this run's `test` job shows `PASS: monitor sweep produced an Event` with a real NDVI-diff `metric_value` (0.008...) and `PASS: the SAME event was delivered over SSE` — 15/15 (up from 13/13, since these two checks now execute meaningfully instead of soft-passing) |

¹ Runs 6 and 7's `ubuntu-22.04`/`windows-latest` legs were still in progress
when the next fix was pushed; the `concurrency` group cancelled them rather
than letting them finish. This is expected behavior, not a masked failure —
each subsequent run re-ran the full matrix from scratch.

## Artifacts — the real deliverable

Run [28938358320](https://github.com/ikerscode/vantage/actions/runs/28938358320)
(and confirmed unchanged in the final run above) produced three real,
downloaded-and-inspected installer artifacts:

| Artifact (workflow artifact name) | Size | Contents (verified by direct download) |
|---|---|---|
| `vantage-launcher-ubuntu-22.04` | ~472 MiB | `deb/VANTAGE_0.1.0_amd64.deb` (64,076,992 bytes), `appimage/VANTAGE_0.1.0_amd64.AppImage` (141,466,104 bytes, executable) |
| `vantage-launcher-macos-latest` | ~60 MiB | `dmg/VANTAGE_0.1.0_aarch64.dmg` |
| `vantage-launcher-windows-latest` | ~118 MiB | `msi/VANTAGE_0.1.0_x64_en-US.msi` (62,496,768 bytes), `nsis/VANTAGE_0.1.0_x64-setup.exe` (61,371,541 bytes) |

Verified genuinely unsigned by downloading and inspecting the actual
artifact contents (not just reading the log) — no `.sig`/signature files
are present in any of the three, consistent with no `APPLE_*`/`WINDOWS_*`
secrets being configured. `rpm` is not built — it's deliberately absent
from `tauri.conf.json`'s configured `bundle.targets`
(`["deb", "appimage", "msi", "nsis", "dmg"]`), not a bug.

## What's genuinely proven

- Every Dockerfile in this stack builds successfully with real Docker, for
  the first time.
- The full `docker compose` stack (db, redis, minio, api, worker, beat,
  tiler, inference) comes up healthy together, for the first time.
- `scripts/smoke.sh` passes 13/13 against **live Sentinel-2** (real Earth
  Search STAC search, real true-color and NDVI tiles, real change-detection
  analysis, real placeholder-detection plumbing, and — as of run #9 in the
  table above — a genuinely-executed monitor-sweep producing a real Event
  over real SSE, not a silently-broken one).
- The weapons-boundary grep, gitleaks, `pip-audit`, and `npm audit` gates
  all run and pass as automated merge gates, not manual checks.
- The Tauri desktop launcher compiles into real, installable bundles on
  Linux, macOS, and Windows, for the first time — confirmed by downloading
  and inspecting the actual files, not just reading build logs.
- Unsigned builds fail gracefully (skip signing) rather than crashing, when
  no signing secrets are configured.

## What's still blocked

- **Code signing**: no `APPLE_CERTIFICATE`/`APPLE_CERTIFICATE_PASSWORD`/
  `APPLE_SIGNING_IDENTITY`/`APPLE_ID`/`APPLE_PASSWORD`/`APPLE_TEAM_ID` or
  `WINDOWS_CERTIFICATE`/`WINDOWS_CERTIFICATE_PASSWORD` repo secrets are
  configured. **This is expected, not a bug** — obtaining an Apple
  Developer Program membership and a Windows code-signing certificate
  requires the operator's own identity and payment; it is not something
  this pipeline can acquire on its own. Gatekeeper/SmartScreen will warn on
  the current unsigned artifacts, exactly as flagged in
  `PACKAGE_REPORT.md`/`INSTALL.md`.
  - **Operator runbook**: obtain the certificates, then `gh secret set
    APPLE_CERTIFICATE < cert.p12.base64` (repeat for each of the 8 secret
    names above, as applicable to the platform(s) you're signing for). No
    workflow change is needed — the export-if-present step already wires
    them through correctly the moment they exist.
- **`release.yml` is unexercised**: no `app-v*` tag has been pushed yet.
  Its build steps are identical to `build-desktop`'s (now proven working),
  but the actual GitHub Release publish step has not been run for real.
  - **Operator runbook**: `git tag app-v0.1.0 && git push origin app-v0.1.0`
    to cut the first real release once ready.

## Security disclosure — historical plaintext secret leak

Runs [28934939975](https://github.com/ikerscode/vantage/actions/runs/28934939975)
and [28935369893](https://github.com/ikerscode/vantage/actions/runs/28935369893)
— both before the masking fix in `11ab636` — have generated dev secrets
(`JWT_SECRET`, `POSTGRES_PASSWORD`, `TILER_TOKEN`, etc.) printed in
plaintext in their `docker compose ps -a` step logs, confirmed by direct
inspection (values are absent from the masked-`***` pattern that appears
in every run after the fix). These logs are still live in this public
repo's Actions history as of this report.

**Assessed impact: low.** Every one of these values is a per-run,
freshly-generated secret (`scripts/generate_dev_secrets.py`, run fresh at
the top of the `test` job) for infrastructure that was fully torn down
(`docker compose down -v`) at the end of that same run. None of them are
long-lived credentials, production secrets, or reused across runs.

**Decision**: not purged. Deleting the old logs would remove the evidence
of the mistake along with the mistake itself, which runs against
CLAUDE.md §3's standard more than the low residual risk justifies. If you
want them purged anyway, GitHub supports deleting a workflow run
(`gh run delete <id>`), which removes its logs; that's your call to make,
not one made unilaterally here.

## What Claude cannot do

Signing certificates (Apple Developer Program enrollment, Windows
code-signing certificate) require the operator's own identity, payment,
and legal signature — they cannot be acquired autonomously by this
pipeline or by Claude. Everything else in Phases 1 and 2 is real,
proven, and running on every push.
