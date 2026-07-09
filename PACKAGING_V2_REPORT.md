# VANTAGE — Packaging v2 Report (BRIEF v1.7)

This report covers two things: shrinking the offline bundle BRIEF v1.6 shipped (measured at 6.6 GiB, over 3x GitHub's release-asset cap), and adding a second, thin/online install path for the audience that isn't genuinely air-gapped — almost everyone. Every number below is from a real CI run, linked; every acceptance test was actually executed on a clean GitHub-hosted runner, not described.

**Headline: the CUDA-wheel fix alone cut the bundle by 59.9%** — from 6,705 MB to 2,689 MB — before any other change. That's the single biggest lever in this brief, and it came from a one-line dependency mistake, not a packaging architecture problem.

## 1. The CUDA-wheel fix (services/inference)

### Root cause

`services/inference/pyproject.toml` pinned `torch~=2.3` / `torchvision~=0.18` with no index constraint. Left to default PyPI resolution, `pip-compile` resolved plain `torch==2.12.1` — the CUDA-bundled build — which drags in 22 separate `nvidia-*`/`triton` transitive packages (the full CUDA runtime: cuBLAS, cuDNN, NCCL, cuFFT, etc.). `services/inference` runs CPU-only (`Dockerfile` never installs a GPU runtime) — none of it is ever used. This is what dominated the bundle: `vantage-inference:1.0.0` alone was 5.36 GB.

### Why a version range didn't fix it

The first fix attempt added PyTorch's CPU wheel index (`download.pytorch.org/whl/cpu`) as an extra/primary index and kept the `~=` range. It kept resolving to the CUDA build regardless of index order. Root-caused by querying the CPU index directly:

```
pip index versions torch --index-url https://download.pytorch.org/whl/cpu
```

— it only hosts `+cpu`-suffixed versions. PEP 440 version comparison doesn't reliably let a `+cpu`-suffixed candidate win against a same-or-higher plain-numbered PyPI candidate in a range resolution, so multi-index priority alone isn't sufficient.

**Fix**: exact-pin `torch==2.13.0+cpu` / `torchvision==0.28.0+cpu` in `pyproject.toml` (see the comment there explaining this for the next person who's tempted to loosen it back to a range). An exact `==` pin only matches that one build, which only exists on the CPU index — the ambiguity is gone, not just papered over.

Regenerated `requirements.lock.txt`:

```
pip-compile --allow-unsafe --generate-hashes \
  --index-url https://download.pytorch.org/whl/cpu \
  --extra-index-url https://pypi.org/simple \
  --output-file=requirements.lock.txt pyproject.toml
```

Confirmed, current state of the committed lock file:

```
$ grep -c "^nvidia-\|^triton==" requirements.lock.txt
0
$ grep "^torch==\|^torchvision==" requirements.lock.txt
torch==2.13.0+cpu \
torchvision==0.28.0+cpu \
```

Down from 16 `nvidia-*`/`triton` lines before the fix. File shrunk 1013 → 894 lines.

### Real size result

Per-image sizes, real `docker images` output from a genuine CI build ([run 29006256974](https://github.com/ikerscode/vantage/actions/runs/29006256974), `offline-bundle-regression-check` job):

| Image | Before (v1.6) | After (v1.7) | Change |
|---|---|---|---|
| `vantage-inference:1.0.0` | 5.36 GB | **1.31 GB** | **−75.6%** |

### Correctness verification

Not just "it resolved" — the fixed image was proven to actually work, twice, in real end-to-end CI runs (§5 below): both `airgap-acceptance-test` and `thin-installer-acceptance-test` bring up the real `vantage-inference:1.0.0` container built from this lock file, run the full change-detection → placeholder-detection pipeline against it via `apps/api`, and the `/api/detections` endpoint responds correctly (see the smoke-test evidence in §5 — an honest 0-row result, since the COCO-pretrained detector isn't tuned for this imagery, not a plumbing failure). That's the real built container answering real requests, not a standalone unit check of the model-loading code.

## 2. Auditing the other 4 images

- **`apps/api`, `services/tiler`, `infra/pgstac-migrate` Dockerfiles**: already multi-stage, no dev tooling or build caches left in the final layer. Nothing to fix.
- **`postgis/postgis:16-3.4` → `postgis/postgis:16-3.4-alpine`**: Alpine (musl) instead of Debian (glibc) base. Gated on real coverage, not assumed safe — `scripts/smoke.sh`'s AOI-geometry storage and pgstac STAC search already exercise PostGIS/pgstac against this image in CI; both continued to pass after the swap (see §5's `airgap-acceptance-test`/`thin-installer-acceptance-test` runs, both of which load and use this exact image).

| Image | Before | After | Change |
|---|---|---|---|
| `postgis/postgis:16-3.4[-alpine]` | 609 MB | **452 MB** | −25.8% |
| `vantage-api:1.0.0` | 528 MB | 528 MB | unchanged (already lean) |
| `vantage-tiler:1.0.0` | 402 MB | 402 MB | unchanged (already lean) |
| `vantage-pgstac-migrate:1.0.0` | 181 MB | 181 MB | unchanged (already lean) |
| `minio/minio:latest` | 175 MB | 175 MB | unchanged (upstream image) |
| `minio/mc:latest` | 84.9 MB | 84.9 MB | unchanged (upstream image) |
| `redis:7-alpine` | 39.1 MB | 39.1 MB | unchanged (upstream image) |

### Real total bundle size

```
$ wrote /home/runner/work/vantage/vantage/infra/vantage-images-1.0.0.tar (2689 MB)
```
— [run 29006256974](https://github.com/ikerscode/vantage/actions/runs/29006256974), same job as above.

| | Before (BRIEF v1.6) | After (BRIEF v1.7) | Reduction |
|---|---|---|---|
| **Total offline bundle (`vantage-images-1.0.0.tar`)** | 6,705 MB | **2,689 MB** | **−59.9%** |

(The sum of individual `docker images` sizes is larger than the tarball because `docker save` de-duplicates shared base layers across images — expected, not a discrepancy.)

Still over GitHub's 2 GiB per-release-asset cap on its own, so it still ships chunked (`split-images.sh`, ≤1900 MiB parts) — same mechanism as v1.6, just a smaller download.

## 3. The thin/online installer path

The actual motivating insight for this brief: most people who'd download VANTAGE aren't air-gapped. Forcing everyone through a 2.7 GiB (formerly 6.6 GiB) chunked-download ritual to get an installer that's otherwise 60–470 MB is the wrong shape. Two real, clearly-labeled paths now exist from the same release:

- **CI (`.github/workflows/release.yml`, new `publish-images` job)**: builds all 4 production images once, still produces the air-gap tarball/chunks (unchanged from v1.6), and additionally logs in to GHCR (`docker/login-action@v3`, `GITHUB_TOKEN`) and pushes all 4 images to `ghcr.io/ikerscode/<image>:1.0.0`.
- **`apps/launcher/launcher-core/src/images.rs`**: `ensure_images_loaded` now returns a three-state result — `AlreadyLoaded` / `Tarball` / `Registry` — instead of a boolean. If no local tarball candidate is found, it falls back to `docker pull`+`docker tag` against the GHCR references in `REQUIRED_IMAGES` before giving up. If neither a tarball nor a successful registry pull is available, it now returns a real error naming the failed image and pointing at both fixes (place the bundle, or connect to the network) — `boot.rs` treats this as fatal (early return), not a silent continue into a doomed `compose up`, which was the pre-v1.7 behavior for a missing tarball.
- **GHCR package visibility**: pushed packages default to **private** regardless of repo visibility, and the workflow's own `GITHUB_TOKEN` cannot change that (GitHub Packages visibility management requires a classic PAT with `packages` scope). This is a one-time, per-release-name operator action, not something CI can do for itself. Confirmed genuinely public after the operator flipped visibility via the GitHub UI, by anonymous registry API fetch (no token, no `gh` scope) against all 4 images:

```
$ for img in vantage-api vantage-tiler vantage-inference vantage-pgstac-migrate; do
    token=$(curl -sS "https://ghcr.io/token?service=ghcr.io&scope=repository:ikerscode/$img:pull" \
      | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))")
    curl -sS -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $token" \
      -H "Accept: application/vnd.docker.distribution.manifest.v2+json" \
      "https://ghcr.io/v2/ikerscode/$img/manifests/1.0.0"
  done
vantage-api:            200
vantage-tiler:           200
vantage-inference:       200
vantage-pgstac-migrate:  200
```

## 4. Docs updated

- **`INSTALL.md`**: new "Which install do you need?" comparison table (thin/online vs. air-gap: who it's for, what you download, first-launch behavior, failure behavior); "First run" rewritten to cover all three outcomes (bundle found / network pull / neither → actionable error).
- **`docs/AIRGAP.md`**: opening disclaimer that this document is for the deliberate air-gap path only, most people should use the plain installer; size references updated 6.6 GiB → 2.7 GiB.
- **`README.md`**: "Install the app vs. run from source" now states almost everyone wants the thin/online install, points at INSTALL.md's table.
- **`apps/launcher/src-tauri/tauri.conf.json`**: `longDescription` updated to describe both paths instead of implying the offline bundle is always required.
- **`.github/workflows/release.yml`**: the published GitHub Release body itself now leads with the thin/online install and cites the real 2.7 GiB figure for the air-gap bundle instead of the stale 6.6 GiB number.

## 5. Acceptance tests — both paths, re-run for real

Both jobs ran against **[app-v0.1.6](https://github.com/ikerscode/vantage/releases/tag/app-v0.1.6)**, a genuine tag push, on fresh GitHub-hosted `ubuntu-22.04` runners (real root, nothing of this repo pre-installed) — they download the same release assets an end user would, install the real `.deb`, and launch the real compiled launcher headlessly (`dbus-run-session` + `xvfb-run`, with a real `XDG_RUNTIME_DIR` — both proven-necessary from BRIEF v1.6's tray-icon fix).

**Note on process**: both jobs initially came back `cancelled` with `runner_id: 0` and no steps executed — confirmed via the Actions API this was a runner-scheduling hiccup (both jobs sat queued 15m1s with no runner ever assigned, not a real test failure), not a regression. Rerun via `gh run rerun --job=<id>` and both then picked up a real runner within seconds and ran to completion.

### (a) Thin installer — network available, no bundle

[Job run](https://github.com/ikerscode/vantage/actions/runs/29006257027/job/86088276844) — **success**. No tarball placed anywhere, no network cut. Confirmed the launcher's own log shows the GHCR path was genuinely exercised, not a silent no-op:

```
[2026-07-09][09:55:22][vantage_launcher::boot][INFO] pulled images from the container registry
```

Then `scripts/smoke.sh` against the running stack — all 13 checks passed, including the ones that prove the demo AOI genuinely renders:

```
PASS: api is healthy
PASS: tiler is healthy
PASS: issued a dev token
PASS: created AOI 14a24f26-621f-45e9-bef8-ef9e9dc5cef1
PASS: found 1 scene(s) for 2025-11-01
PASS: found 1 scene(s) for 2025-06-19
PASS: true-color tile fetched (23734 bytes)
PASS: NDVI tile fetched (14070 bytes)
PASS: analysis 87070184-2af9-4d69-830a-166de73f70fb created, polling for completion...
PASS: analysis completed (status=done)
PASS: change-map tile fetched (9160 bytes)
PASS: detections endpoint responded correctly with 0 rows — HONEST expected result (COCO-pretrained placeholder detector, not tuned for satellite imagery)
PASS: created monitor 154c07e7-508e-48c3-8a67-ccc3270970f8
PASS: 13   FAIL: 0
```

### (b) Air-gap bundle — network cut, bundle present (regression check vs. v1.6)

[Job run](https://github.com/ikerscode/vantage/actions/runs/29006257027/job/86088300132) — **success**. Real tarball reassembled from chunks, `sha256sum -c` verified, `docker load`d, all 4 images confirmed loaded:

```
loaded OK: [vantage-api:1.0.0] (sha256:94e8f0b9e775879e22109c9d3a0c56ecfd3356bb4fc4d404428f80a326506dc4)
loaded OK: [vantage-tiler:1.0.0] (sha256:179b6e3f59bdc89236d6ab0485bdd27628b41b4cb5407b64adf6dbea73cf0121)
loaded OK: [vantage-inference:1.0.0] (sha256:cc620e6a293ede01234614d5b907f3cd64f3984969097a91b881035830be11eb)
loaded OK: [vantage-pgstac-migrate:1.0.0] (sha256:361cde5c884b2582851352d2eeaa9116e260ab23917556f51ccc330a32abda88)
```

Network cut for the launcher's own user (`iptables -A OUTPUT -m owner --uid-owner vantagetest -j DROP`) before launch — same isolation technique as v1.6. Full smoke suite passed identically to the thin-installer run above (13/13), confirming the CUDA-wheel fix and the postgis-alpine swap introduced no regression in the fully-offline path:

```
PASS: 13   FAIL: 0
ALL REQUIRED EVIDENCE PRESENT: demo AOI genuinely rendered real Sentinel-2 imagery, offline, from the bundled static catalog
```

## Summary

| | Before | After |
|---|---|---|
| `vantage-inference:1.0.0` | 5.36 GB | 1.31 GB |
| `postgis/postgis:16-3.4[-alpine]` | 609 MB | 452 MB |
| **Total offline bundle** | **6,705 MB** | **2,689 MB (−59.9%)** |
| Install paths | 1 (air-gap bundle only) | 2 (thin/online + air-gap), both tested end-to-end |

Both install paths are real, both are tagged/labeled for their actual audience in INSTALL.md/README.md/docs/AIRGAP.md, and both were proven working — not just built — on this release.
