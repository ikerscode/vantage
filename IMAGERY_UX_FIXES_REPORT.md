# VANTAGE — Imagery loading & overlay UX fixes

**Scope:** the live-testing feedback about imagery not loading until reload, the
"Something went wrong" toast, Change blanking the imagery, detection/change
styling, and the black-void-on-load. All changes are frontend + one backend
color constant.

**Verification honesty (CLAUDE.md §3):** this sandbox has no Docker/Postgres, so
I did **not** stand up the live stack for this pass. What actually ran:

- `apps/web` → `npm run build` (`tsc -b && vite build`) — **passes**, 0 type errors.
- `packages/geo` → `pytest` — **14 passed** (includes the change-colorizer test).

The behavioral fixes below are traced to specific root causes in the code, but
"loads on first try now" is **reasoned from the code**, not yet observed on a
live install. Drive it end-to-end on a Docker-capable machine to confirm.

---

## 1. "No imagery until I reload the page every time I make an AOI"

Two independent bugs stacked to produce this; both are fixed.

**1a. Stale scene results across AOI switches.** `useStacSearch` was a
`useMutation`, so its `data` was a single component-local result with no tie to
which AOI it belonged to. Selecting/creating a new AOI updated `selectedAoiId`
immediately while the *previous* AOI's scenes were still in `data`. The
scrubber's auto-pick effect (`autoPickedForAoi` guard) then latched the new AOI
onto an **old, non-covering scene** and refused to correct itself once the real
results arrived — the map had flown to the new AOI but was pointed at a scene
located somewhere else, i.e. "no imagery." A full reload wiped the state and the
search ran cleanly, which is exactly why reloading "fixed" it.

→ Converted scene search to a **query keyed by `(aoi_id, date_from, date_to)`**
(`api/stac.ts` `useStacScenes`). A keyed query returns `undefined` while a new
key is in flight (no stale carry-over) and caches per AOI. `TemporalScrubber`'s
manual auto-search effect is gone (the query fires on selection automatically).

**1b. Raster source never updated its URL.** `syncRasterLayer` only added a
source when one was missing and otherwise left it alone. A source's tilejson URL
can't be mutated in place, so when the scene changed (new URL) the layer kept
serving the **previous** AOI's imagery until a reload tore the map down. Fixed by
tracking each source's URL (`rasterSourceUrls` ref) and rebuilding the source
when it changes.

## 2. "Something went wrong" toast, then works after refresh

The global toast (`main.tsx`) fires on **any** query/mutation error. Its most
common trigger was 1a/1b above plus the scene search firing before the auth
token existed (the mutation had no token gate, unlike `useAois`). Fixes:

- `useStacScenes` is **token-gated** (`enabled: !!token`) — never fires
  unauthenticated, so no first-load 401→toast.
- Every `ApiError` now carries a stable **code** shown in the toast title:
  `VG-<httpStatus>` (e.g. `VG-401`, `VG-500`), `VG-TIMEOUT`, or `VG-NET`. So if
  a genuine error does occur, the user can report exactly which one instead of a
  generic message.

## 3. Selecting Change blanked the imagery

`activeRasterLayer` was one mutually-exclusive slot across
`true_color | ndvi | change`, so selecting Change deselected the base imagery.
Re-modeled the layers:

- **Base** (`true_color | ndvi`) is a radio — exactly one is always on.
- **Change** and **Detections** are independent **overlays** that stack on top.
  The change raster is inserted beneath nothing / above the base (`beforeId`
  ordering), so True Color / NDVI **stays on** underneath it.

`LayersControl` reflects this (base radios + two overlay toggles). Clicking a
change result / running an analysis now auto-enables the Change overlay.

## 4. Detections = red, Change = orange, both **pulsing**; outlined

Both overlays share **one `requestAnimationFrame` loop** that computes a smooth
cosine brightness level (a real breathe in/out, not a hard on/off blink).
Chosen deliberately over a deck.gl/MapLibre transition: deck.gl composite layers
don't forward `transitions` to their sublayers, so that route would have
silently degraded to a blink. The loop is paused while drawing and quantized to
~2% steps so it idles most of the cycle.

- **Detections** (vector bboxes): red (`#f85149`), outlined in the shape of each
  box, alpha follows the pulse level. Selected box holds a steady bright highlight.
- **Change** (raster footprint): recolored to the **orange** family in
  `vantage_geo/diff.py` (`LOSS_COLOR`/`GAIN_COLOR`); its `raster-opacity` is
  driven by the same pulse level.
  - The footprint is filled (in the shape of the change), not a crisp vector
    outline — a true vectorized outline would need the backend to emit change
    contours (noted as a follow-up).
  - **Only analyses colorized after this change are orange**; COGs already
    written keep their old red/green. Re-run an analysis to get orange.

## 5. Change/detection coverage — troubleshooting result

- **Change detection is global, not USA-only.** Default imagery is Earth Search
  (global Sentinel-2). The *only pre-seeded* change result is the
  "Demo — Central Valley, CA" AOI, which is where the "only USA" impression comes
  from. Soweto and Camposampiero finding changes **confirms** it works anywhere.
- **0 detections everywhere is expected, not a bug.** The bundled detector is a
  COCO-pretrained Faster R-CNN (generic classes: person/car/boat…). It
  essentially never fires on 10 m/px top-down satellite chips (512 px ≈ 5 km).
  This is the honest "placeholder detection" seam (CLAUDE.md §3/§4 — no bundled
  overhead dataset; YOLO/AGPL forbidden). Made this explicit in the UI (a note
  under the Detections toggle) rather than faking detections. The opt-in
  `torchvision_fasterrcnn_vessel` backend can find **ships**, but only over
  water — inland AOIs (Soweto/Camposampiero) will still show nothing.
- **Large AOIs only partially load imagery.** v1 requires a *single* scene to
  cover the whole AOI (`pick_best_scene`). A ~48,000 km² AOI is far larger than
  one ~110 km Sentinel granule, so only one granule's patch renders (matches the
  screenshot). Multi-scene mosaicking is the deferred v2 fix; for now, smaller
  AOIs load fully.

## 6. Black void on load / zoom-out clamp / snappier pan

- `MIN_ZOOM = 10` (~119 km view radius) keeps the camera from zooming out into
  open void (was Z5 ≈ continental). Initial store zoom raised 5 → 10 to match.
- First auto-navigation now **jumps** (instant) to the AOI instead of a
  multi-second fly across empty void.
- Raster tiles get `raster-fade-duration: 0` so they pop in the instant they
  arrive instead of cross-fading — panning feels markedly snappier. (Tiles are
  still computed on demand by the tiler — no pre-rendering, per CLAUDE.md §2.)

Note: with no basemap (air-gap invariant), anywhere without imagery is
intentionally void; these changes minimize how much of it you ever see, but
can't replace it with a Google-Earth basemap without violating §2.

---

## 7. Interaction feedback + design amplification (second pass)

Goal: no control ever feels like a dead/ghost button, everything is smooth, and
the console reads cleaner. All within CLAUDE.md §5 (one cyan accent for chrome,
observation-not-engagement) — the tactical palette was *amplified*, not replaced.

- **Global activity bar** (`GlobalActivityBar.tsx`): a slim indeterminate sweep
  on the top edge whenever *any* react-query request is in flight
  (`useIsFetching` + `useIsMutating`). App-wide "we heard you, working" signal.
- **Inline spinners + busy states** on every async button: AOI **Save**
  (`SAVING…`), **Search** (`SEARCHING…`), **Run Analysis** (`SUBMITTING…`), and
  the per-row **Archive** (spinner on the exact row via `mutation.variables`).
  Buttons take a `.btn-busy` accent treatment while in flight.
- **"Loading imagery" chip** on the map: tile fetches bypass react-query, so a
  MapLibre `sourcedataloading`/`idle` pair drives a small chip so late tiles
  read as "working" too.
- **Press / hover / focus everywhere**: a consistent `:active` depress
  (`scale .97`), keyboard `:focus-visible` accent ring, filled-in hover
  affordances on buttons that lacked them, and consistent `:disabled` styling.
- **Smoothness**: shared easing/transition tokens; panels fade-up on mount;
  toasts slide in and animate between stack positions; hovered list rows reveal
  an accent edge. All gated behind `prefers-reduced-motion`.
- **Cleaner colorization**: a restrained accent gradient on primary/commit
  buttons (Save-as-Monitor), a machined-glass hairline highlight on panels, and
  a single reusable focus-ring token.

Note on "militia colourisation": I did **not** swap the accent hue — CLAUDE.md
§5 locks it to one cool cyan, so I sharpened that palette instead of replacing
it. If you want a different accent (amber/tactical-green/etc.), it's a one-token
change (`--accent` / `--accent-bright` / `--accent-dim` in `styles.css`) — say
the word and I'll swap it.

## Files touched (passes 1–2)

Frontend: `api/client.ts`, `api/stac.ts`, `store/{analysis,map,toast}Store.ts`,
`main.tsx`, `App.tsx`, `components/{MapCanvas,LayersControl,TemporalScrubber,`
`ResultsFeed,AOIPanel,GlobalActivityBar}.tsx`, `styles.css`. Backend:
`packages/geo/src/vantage_geo/diff.py`.

---

## 8. Full audit, operator features, security + architecture (third pass)

Verification up front (this sandbox has podman but the checks below are what
ran): `apps/web` `tsc -b` + `vite build` clean; **geo 14 / api 36 / tiler 13**
unit tests pass; weapons-boundary gate green.

**Code analysis.** All suites green. Fixed a real defect I'd introduced: the
graticule (below) first rebuilt every deck vector layer on each pan, which
could churn the editable draw layer mid-draw — moved it to a native MapLibre
line layer updated imperatively on `moveend`.

**Design (against the artifact-design skill's AI-tell list).** Verdict: not in
cliché territory — near-black+cyan is the project's *own locked system* (not a
lone random pop), IBM Plex (engineered) not Inter/Space-Grotesk, restrained
radii, edge-anchored not centred. Added, tastefully: an honest **boot
sequence** (`BootSequence.tsx`) tied to real auth/tiler readiness with a
min-dwell + hard-timeout + reduced-motion skip; a client-side **graticule**
(real lat/lon structure over the void — subject-true, air-gap safe); a subtle
optical **vignette**; cool-biased neutrals; instrument tick before panel titles.

**Operator features (analysis-only, inside CLAUDE.md §1).** **MGRS** — the
coordinate frame NATO/allied forces actually use. New `lib/mgrs.ts` (WGS84↔UTM↔
MGRS), wired as a live `GRID` readout in the status strip and as grid-reference
input in the command bar (type "18S UJ 2340 0645" to navigate). Verified: the
meridional arc matches the textbook M(45°) constant exactly, Null Island exact,
and forward→inverse round-trips to **sub-metre** across both hemispheres. The
in-parallel **compass / north-up** control was completed alongside.

**Security (network-engineer pass).** Findings fixed:
- Tiler and inference shared-token checks used a plain `!=` — a timing
  side-channel on the secret. Now `hmac.compare_digest` (matching the dev-token
  path). (`services/tiler/app/security.py`, `services/inference/app/security.py`)
- `DEV_TOKEN_SECRET` — which grants token issuance from *any* origin when set —
  was not covered by the SEC-04 production weak-secret refusal. A short custom
  value was remotely brute-forceable. Now refused in production (default stays
  allowed because it's deliberately disabled). Regression tests added.
  (`apps/api/app/core/config.py`, `tests/test_config.py`)
- Reviewed and confirmed already-solid: DNS-rebinding-aware SSRF gate + `s3://`/
  `file://` path-traversal resolution (tiler), SSE auth via `Authorization`
  header (no token-in-URL), decompression-bomb caps wired (`Image.MAX_IMAGE_PIXELS`
  + content-length), parameterised SQLAlchemy (no raw SQL), specific CORS origins.
  Residual (documented, not quick-fixable): app-level SSRF DNS check has an
  inherent TOCTOU window vs. GDAL's fetch; CORS `*` isn't explicitly refused in
  prod.

**Architecture / bloat.** Untracked `run_artifacts/` (20 files, regenerable run
outputs — already in `.gitignore`, never written by CI, so tracking them was an
inconsistency); removed a stray `vite.config.d.ts` build artifact and ignored
it. **Did not delete** the `*_REPORT.md` audit trail — CLAUDE.md §3/§6 treats
those as load-bearing "prove-it" evidence, so removing them would destroy
traceability, not reduce bloat. No orphaned source files found.

New files: `components/BootSequence.tsx`, `components/Compass.tsx`, `lib/mgrs.ts`.
