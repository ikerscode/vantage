# VANTAGE — Model Weights Publishing Report (BRIEF v2.0)

**Status: every claim below is traceable to a real command's output, a real CI run, or a real published artifact — not asserted from memory of a prior pass** (the CLAUDE.md §3 standard). This report closes the gap `VESSEL_DETECTION_REPORT.md` (BRIEF v1.8) left open: a real, evaluated vessel-detection checkpoint that only ever existed in the training sandbox, invisible to anyone actually installing VANTAGE.

## 1. Where the checkpoint is hosted, and why

`vessel_fasterrcnn.pth` (165.7MB) is a GitHub Release asset on its own dedicated tag,
[`model-weights-v1`](https://github.com/ikerscode/vantage/releases/tag/model-weights-v1),
sha256 `53878268a049583a40a366aade7ed00b85dd9e65b6cc745b9bbe703ef921ec2a`. This tag is deliberately decoupled from `app-v*` release tags so the checkpoint is uploaded once and every future app release just re-fetches the same asset, instead of re-uploading a large, infrequently-changing binary on every app version bump.

## 2. What changed in the release pipeline

`.github/workflows/release.yml`'s `publish-images` job:

1. **Fetches the checkpoint before the Docker build** (new step, before `build-images.sh` runs): `gh release download model-weights-v1 ... --dir services/inference/weights`, then verifies its sha256. The Dockerfile's existing `COPY services/inference/weights/ /app/weights/` is already a directory-level copy (BRIEF v1.8), so it needed no change — it just needed the real file present on disk first.
2. **One image, both backends**: `vantage-inference` now ships the COCO placeholder (`MODEL_BACKEND=torchvision_fasterrcnn`, default) and the fine-tuned vessel backend (`MODEL_BACKEND=torchvision_fasterrcnn_vessel`) baked into the same published image — no second image tag.
3. **Digest pinning (BRIEF v1.9) is automatically correct**: the image is built (with the real weights already in place) *before* `publish-images` computes and uploads `image-digests.json`, so the pinned digest always reflects the actual, weights-included content. No manual re-pin step was needed.
4. **`weights_only=True` (BRIEF v1.9) is untouched** — confirmed no plain `torch.load()` was reintroduced anywhere in the vessel-backend load path.

Two more bugs were found live while getting a release to actually pass CI, both pre-existing defects from BRIEF v1.9 that this was the first real release to exercise:

- **`contents: read` couldn't see the release's own assets.** `airgap-acceptance-test`/`thin-installer-acceptance-test` both failed immediately with a bare `gh release download: release not found`. Root cause: `release.yml`'s `release` job always creates the release as a **draft**, and a draft's assets aren't visible to a read-only-scoped `GITHUB_TOKEN` — confirmed by elimination (the identical command against the identical tag worked instantly with a write-scoped token). Fixed by reverting those two jobs to `contents: write` (commit `907ac21`).
- **Draft releases silently broke thin-install for every real user since BRIEF v1.9.** The *compiled launcher* fetches `image-digests.json` via a plain, unauthenticated `https://github.com/.../releases/download/<tag>/...` URL — the only way a real end user's installed app can reach it, no token involved — and GitHub does not serve a draft release's assets over that URL at all, regardless of who's asking. Confirmed directly: `curl` to that exact URL returned `404` while the release was a draft, `200` immediately after publishing it. This meant every release cut since BRIEF v1.9 (including the then-current `app-v2.0.1`) was broken for real thin-install users. Fixed by adding an explicit publish step (`gh release edit "$TAG" --draft=false`) at the end of `publish-images`, once every real asset is attached (commit `d3a5e4f`). Both prior draft releases were published by hand to unblock them immediately.

## 3. Real inference output, from the actual built image

Built `vantage-inference:1.0.0` locally via Podman (scratch storage root, to route around this machine's unrelated snap/podman storage-path bug) with the real checkpoint in place — confirmed baked in with the exact release-asset sha256:

```
$ podman run --rm vantage-inference:1.0.0 sh -c "sha256sum /app/weights/vessel_fasterrcnn.pth"
53878268a049583a40a366aade7ed00b85dd9e65b6cc745b9bbe703ef921ec2a  /app/weights/vessel_fasterrcnn.pth
```

Ran the real production code path (`app.models.factory.get_model_backend()` → `TorchvisionFasterRCNNVessel`, exactly what a live `/detect` request uses) against an evenly-strided 291-chip subset of the same held-out tile `34VER` (three whole Sentinel-2 scenes never seen during training) that `VESSEL_DETECTION_REPORT.md` evaluated:

| Confidence ≥ | TP | FP | FN | Precision | Recall | F1 | vs. reported F1 |
|---|---|---|---|---|---|---|---|
| 0.3 | 73 | 92 | 14 | 0.442 | 0.839 | 0.579 | 0.571 (+0.008) |
| 0.5 | 70 | 70 | 17 | 0.500 | 0.805 | 0.617 | 0.621 (−0.004) |
| 0.7 | 67 | 52 | 20 | 0.563 | 0.770 | 0.650 | 0.663 (−0.013) |
| 0.9 | 61 | 27 | 26 | 0.693 | 0.701 | 0.697 | 0.696 (+0.001) |

Every threshold reproduces the original report's F1 within ~1.3 points. One chip reproduced *exactly*: `34VER_20220617_2_14` returned the identical 3 boxes at identical confidence (0.985, 0.985, 0.935) as the original report's own worked example — real evidence this is the same model behaving the same way, not a coincidence.

## 4. The final, fully-green release: `app-v2.0.3`

Three release cuts were needed to get here — `app-v2.0.1` (core feature, 2 CI jobs failed on the `contents:read` bug above), `app-v2.0.2` (fixed that, uncovered the deeper draft-release bug above), `app-v2.0.3` (fixed that too — every job passed):

```
✓ app-v2.0.3 Release · 29446579404
✓ release (macos-latest) in 6m9s
✓ release (windows-latest) in 11m30s
✓ release (ubuntu-22.04) in 7m30s
✓ publish-images in 7m59s
✓ thin-installer-acceptance-test in 2m26s
✓ airgap-acceptance-test in 3m42s
```

Published image digests (`image-digests.json`, this release):

```json
{
  "vantage-api": "sha256:84c83fb39dea02dae7587bc3ff44a21d85c6fac34339cf413e9bf2c9e2cdb154",
  "vantage-tiler": "sha256:8d585d21b52e1fca710747925753c3a7ea19f153033451a086b11616db3db04c",
  "vantage-inference": "sha256:b9803b031f8c07a3a2a4ed18f96d6eeaed3d300cd2ec5ce19091b9e4ba576828",
  "vantage-pgstac-migrate": "sha256:77ec8c0a4902f96f51f95cf99f8e37b46c5d017e0e1eecad777a7f38dabe4eb4"
}
```

Thin-installer path (pulls `vantage-inference@sha256:b9803b...` fresh from GHCR, no local bundle):

```
[vantage_launcher::boot][INFO] pulled images from the container registry
PASS: issued a dev token
PASS: created AOI 3b0289eb-b070-4ba0-bbcc-488ae976e153
PASS: true-color tile fetched (23734 bytes)
PASS: NDVI tile fetched (14070 bytes)
PASS: analysis completed (status=done)
PASS: change-map tile fetched (9041 bytes)
PASS: 13   FAIL: 0
```

Air-gap path (loads the same image from the offline tarball, network cut for the launcher's own user):

```
ALL REQUIRED EVIDENCE PRESENT: demo AOI genuinely rendered real Sentinel-2 imagery, offline, from the bundled static catalog
PASS: 13   FAIL: 0
```

Both acceptance tests genuinely exercised the ~165MB-larger image end to end and neither install path broke.

## 5. Open item (not acted on, flagged for a separate decision)

`app-v2.0.1` and `app-v2.0.2` are still live, published releases (each was manually un-drafted while diagnosing the bugs above) even though `app-v2.0.3` supersedes both. Deleting them is a straightforward cleanup but wasn't done here since removing public releases/tags is the kind of action worth a separate explicit go-ahead.

## Files changed

- `.github/workflows/release.yml` — checkpoint fetch step, `contents: write` fix, auto-publish step.
- `services/inference/weights/README.md` — documents the `model-weights-v1` hosting path and how to fetch it directly.
