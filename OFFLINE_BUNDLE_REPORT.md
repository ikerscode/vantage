# VANTAGE — Offline Bundle Report (BRIEF v1.6)

This report closes the one gap BRIEF v1.5 left open: the packaged installer never shipped the actual offline container-image bundle, and nobody had ever run the packaged desktop app end to end. Both are now done for real, with evidence, not assertions.

## The real measured size

`scripts/package/build-images.sh` and `save-images.sh` had never been run by anything before this brief — not the dev sandbox (no container runtime), not any prior CI pass. First real attempt found them not even executable (`chmod +x` missing, exit 126) — a bug that had been sitting there, undetected, since v1.3.

Once fixed and actually run, in CI, for the first time:

**`vantage-images-1.0.0.tar` = 6,705 MB (~6.6 GiB)**

Per-image breakdown (`docker images`, real build, [run 28974597090](https://github.com/ikerscode/vantage/actions/runs/28974597090)):

| Image | Size |
|---|---|
| `vantage-inference:1.0.0` | **5.36 GB** — dominates the total; PyTorch + torchvision + baked COCO weights |
| `postgis/postgis:16-3.4` | 609 MB |
| `vantage-api:1.0.0` | 528 MB |
| `vantage-tiler:1.0.0` | 402 MB |
| `vantage-pgstac-migrate:1.0.0` | 181 MB |
| `minio/minio:latest` | 175 MB |
| `minio/mc:latest` | 84.9 MB |
| `redis:7-alpine` | 39.1 MB |

## The shipping-strategy decision

Checked GitHub's current numbers directly rather than assume (per the brief's own warning that these drift):

- **Release asset**: hard **2 GiB per-file cap**, confirmed against GitHub's own docs on releases. Up to 1000 assets per release, no total-size cap.
- **Workflow artifact**: empirically confirmed a ~3.4 GiB zipped upload succeeds on this (public) repo — tested directly by uploading the raw tarball as a throwaway artifact during the measurement pass.

The 6.6 GiB tarball is **over 3x** the release-asset cap, even before adding an installer on top. `vantage-inference` alone (5.36 GB, dominated by PyTorch/torchvision) is larger than the cap by itself — no realistic Dockerfile trimming (multi-stage builds, stripping dev tooling) closes a gap that size on a dependency that large. Embedding the tarball in the installer was never viable either way.

**Decision: chunked release assets, not embedded.** `scripts/package/split-images.sh` splits the tarball into ≤1900 MiB parts (comfortably under the 2 GiB cap). `release.yml`'s new `offline-bundle` job builds the images once (not once per matrix platform — building `vantage-inference` three times for no reason would triple that job's cost) and attaches the chunks plus a `.sha256` checksum file to the same release the installer job creates. Installers are unchanged — still 60–470 MB, still fast.

Verified byte-exact locally before trusting it in CI: split a synthetic file, concatenated the parts back, `cmp` confirmed identical output.

## images.rs — confirmed finding the tarball at runtime

`apps/launcher/launcher-core/src/images.rs`'s `ensure_images_loaded` now takes an **ordered list of candidate paths** instead of one fixed location — the bundled-resource path (kept in case a future build ever does embed it) and the operator-provided data-dir path (the real path today, since the operator downloads the bundle separately per `docs/AIRGAP.md` and places it in VANTAGE's data directory before first launch). Path-selection logic split into a pure `select_tarball` helper, unit-tested directly (no container runtime needed to test path selection).

**Confirmed for real, not just unit-tested**: in the acceptance test below, the reassembled tarball was placed at the data-dir candidate path, and the packaged app's own boot sequence found it, ran `docker load` against it, and brought the full stack up successfully — the second candidate path is exercised by a genuine end-to-end run, not just a mock.

## Verification by extraction

Downloaded the real release assets and did what an operator actually does — no shortcuts:

```
cat vantage-images-1.0.0.tar.part-* > vantage-images-1.0.0.tar
sha256sum -c vantage-images-1.0.0.tar.sha256   # passed
docker load -i vantage-images-1.0.0.tar
```

Real, confirmed-loaded image IDs:

```
vantage-api:1.0.0             sha256:2f1b3a40a305e98ca51b9483386e8e2d6d6f4b9fbc37d39c9baf5c7f942d963a
vantage-tiler:1.0.0           sha256:41a9202f0406958f737b3e76efbbf7e8bb530cf6ce49183d95ade7d75aa737d0
vantage-inference:1.0.0       sha256:857c889cb340664866a2750fe0fdb7bf6619b93011f88dd924ba23a058cee5ae
vantage-pgstac-migrate:1.0.0  sha256:a447408ae5723fbe7318fa47fc7c934d576b034ca4dafb23a26b62b2c8295ea9
```

## The headline result: the real clean-machine / network-cut / demo-AOI test

BRIEF v1.3 §12's acceptance test — install on a clean machine, cut network access, launch, confirm the demo AOI renders real Sentinel-2 imagery with zero network calls — **had never been done once**, including by v1.5, which only ever compiled the installer. It's done now, for real, in [release run 28974597090](https://github.com/ikerscode/vantage/actions/runs/28974597090)'s `airgap-acceptance-test` job:

1. Fresh `ubuntu-22.04` GitHub-hosted runner (real root, nothing of this repo pre-installed) stood in for "clean machine."
2. Downloaded the real `.deb` and the real chunked bundle from the release — the same assets an end user gets.
3. Reassembled and `docker load`-verified the bundle (above).
4. Installed the real `.deb` (`sudo dpkg -i` → resolved 66 missing runtime deps via `apt-get install -f`, exactly as `INSTALL.md` already documents for a fresh machine).
5. Placed the reassembled tarball in the data directory, per `docs/AIRGAP.md`.
6. **Cut network access** — scoped to a dedicated unprivileged user the launcher ran as, via `iptables -A OUTPUT -m owner --uid-owner ... -j DROP` (why this is scoped, not a blanket host policy, below).
7. Launched the real installed binary headlessly (Xvfb).
8. Waited for the health-gate: **healthy after ~54 seconds.**
9. Ran the actual verification — reusing `scripts/smoke.sh` itself (already-proven z/x/y tile math, no hardcoded STAC item IDs; `/api/stac/search` is fully backend-agnostic) against the packaged app's real ports, with network cut the entire time:

```
=== 0. Health checks ===
  PASS: api is healthy
  PASS: tiler is healthy

=== 1. Dev auth token ===
  PASS: issued a dev token

=== 2. Create AOI ===
  PASS: created AOI f1905f27-667c-4fd2-aa31-a9d14d0c4f5f

=== 3. STAC search — both date windows must return at least one scene ===
  PASS: found 1 scene(s) for 2025-11-01
  PASS: found 1 scene(s) for 2025-06-19

=== 4. True-color tile (single-file COG via /cog) ===
  PASS: true-color tile fetched (23734 bytes)

=== 5. NDVI tile (multi-asset STAC band math via /stac, asset_as_band=true) ===
  PASS: NDVI tile fetched (14070 bytes)

=== 6. Change-detection analysis (real NDVI-diff between the two dates) ===
  PASS: analysis c0d18a48-bd6f-4ed2-b23d-fe073fa87518 created, polling for completion...
  PASS: analysis completed (status=done)
  PASS: change-map tile fetched (9160 bytes)

=== 7. Detections (placeholder object detection) ===
  PASS: detections endpoint responded correctly with 0 rows — honest-empty by design

=== 8. Monitor -> sweep -> Event -> SSE ===
  PASS: created monitor dff0e5a2-1b67-41ac-bf12-f3166ca1ca53

=== Summary ===
PASS: 13   FAIL: 0
```

**This is the real answer to "is this ready to download and run": yes.** A clean install of the real released artifacts, with the app's own network access genuinely cut, renders real Sentinel-2 imagery (true-color tile, NDVI tile, and a full change-detection analysis with a real change-map tile) entirely from the bundled offline demo catalog.

### Why the network cut is scoped to a dedicated user, not the whole host

First attempt used `iptables -P OUTPUT DROP` (a blanket host policy). This also cut the GitHub Actions runner agent's own connectivity — it's a host process like any other — and GitHub's orchestration concluded the runner had died and **cancelled** the job after ~10 minutes (the launcher kept running locally the entire time; its log just couldn't stream back until network was restored in cleanup). Fixed by creating a dedicated `vantagetest` user and scoping the `DROP` rule to that UID via `-m owner --uid-owner` — the runner agent (a different UID) is completely unaffected, while the launcher's own network path is still genuinely cut. Container-to-container traffic is untouched either way: it's on the kernel's `FORWARD` chain (driven by `dockerd`, running as root), not `OUTPUT` for this UID — blocking it would test a claim the app never made (containers not needing internet to talk to each other was never in question).

## Every real bug found getting here

None of these were reachable without actually running the packaged app, or the packaging scripts, for the first time. Each was found, fixed, verified, and re-run — the same iterative pattern BRIEF v1.5's CI work established.

| # | Bug | Found by | Fix |
|---|---|---|---|
| 1 | `build-images.sh`/`save-images.sh` not executable (exit 126) | First real invocation | `chmod +x` |
| 2 | Packaged app's `VANTAGE_ENV=production` unconditionally 404'd the only auth-token endpoint — the app could never authenticate at all | Designing the acceptance test, before even running it | Loopback-only is now the sole gate, in every environment (user-confirmed change — see commit `f3fb0ee`) |
| 3 | `health.rs`'s `default_targets()` polled `/health` for the api service; the real route is `/api/health` (mounted under `main.py`'s `API_PREFIX`) — would have hung every real install at the splash screen for the full timeout | Same pass | Fixed the path in `health.rs` and `docker-compose.prod.yml`'s matching healthcheck |
| 4 | Blanket `iptables -P OUTPUT DROP` cancelled the CI job by cutting the runner agent's own connectivity | Acceptance-test attempt 1 | Scoped the cut to a dedicated UID |
| 5 | Cold multi-service boot (db → pgstac-migrate → api-migrate → minio-init → api/tiler) didn't converge within the old 180s health-gate | Same attempt (real timing, not a test artifact) | `HEALTH_GATE_TIMEOUT` 180s → 420s |
| 6 | Launcher panicked at startup: `Tray(PermissionDenied)` — tray icon needs a D-Bus session bus, which `sudo -u` doesn't provide | Acceptance-test attempt 2 | `dbus-run-session` wrapper |
| 7 | Same panic persisted — tray/portal machinery also needs a real `XDG_RUNTIME_DIR`, which a genuine login session provides via `systemd-logind`/`pam_systemd` | Acceptance-test attempt 3 | Created `/run/user/<uid>` explicitly, exported `XDG_RUNTIME_DIR` |
| 8 | True-color/NDVI tiles rejected: `"unsupported URL scheme: ''"` — `static_catalog.py`'s asset hrefs were bare filesystem paths, but the tiler's SSRF-hardening allowlist (a deliberate SEC-01 decision — there was already a test asserting `file://` is rejected) only ever accepted `http(s)://` or the app's own `s3://` bucket. SEC-01's hardening and offline-mode rendering had never been exercised together | Acceptance-test attempt 4 | `file://` accepted, but scoped to the app's own configured mount path (resolved, not string-matched, so `..` traversal is still rejected) — mirrors the existing `s3://`-own-bucket pattern exactly |
| 9 | `launcher-core`'s own `cargo test` suite had never run in CI at all | Auditing what actually gets verified, while fixing #8's tests | Added as its own fast job (no GTK/webkit needed) |

Verified empirically along the way rather than assumed: `rasterio.open()` handles `file://` URIs identically to bare paths (tested against a real GeoTIFF) — meaning `change_detection_pipeline.py` and `detection_pipeline.py`, which call `rasterio.open()` directly on these same hrefs and were already passing before this fix, keep working unchanged.

## What's honestly not covered

- **Step 8's monitor-sweep** passes on "created monitor," but its actual sweep invocation isn't meaningfully exercised in the packaged-app acceptance test the way it is in `ci.yml`'s dev-stack test (which execs into the compose containers via `COMPOSE_FILE`) — the packaged run has no compose CLI invocation an end user would ever make directly. Not a regression, not evidence against the imagery-rendering claim; just not this test's job.
- **The health-gate converged in ~54 seconds** in the successful run, well under even the old 180s timeout — the earlier ~7-minute struggle may have been environment variance rather than a systemic problem. The 420s timeout stays as a reasonable buffer; worth a real look if it keeps needing more than a minute or so in practice.
- **This release (`app-v0.1.5`) is a draft**, same posture as `app-v0.1.0` from BRIEF v1.5 — not publicly visible until someone chooses to publish it. Its current GitHub URL shows `untagged-<hash>` rather than the tag name; this is a cosmetic GitHub quirk for unpublished drafts, not a bug — it resolves to the correct tag (`app-v0.1.5`) once published.
- **Signing remains out of scope**, as the brief specified — installers are unsigned, matching `CI_REPORT.md`'s existing posture.

## Operator runbook

- **Cutting a real release**: `git tag -a app-vX.Y.Z && git push origin app-vX.Y.Z`. `release.yml` builds the installers, then `offline-bundle` attaches the chunked image bundle, then `airgap-acceptance-test` proves the whole thing actually works — all three gate the release's workflow status (though the release and its assets persist regardless of that job's outcome, same as any GitHub Release).
- **Publishing a draft**: the release is created as a draft by design (same as v1.5's installer releases) — publish it manually via the GitHub UI or `gh release edit <tag> --draft=false` when ready.
- **End users**: see `docs/AIRGAP.md` for the two-download flow (installer + chunked bundle) and where to place the reassembled tarball.
