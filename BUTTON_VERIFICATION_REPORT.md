# VANTAGE — Full Interaction Verification (BRIEF v2, overnight pass)

Requested: "verify every button does what it's supposed to do and it's bugless."
Method: every API-backed action driven live against the running stack (real
requests, real responses); every UI-only interaction cross-checked against
its store wiring in code. Nothing below is asserted from reading alone where
a live check was possible.

## Result summary

Every interactive surface works. The imagery pipeline, run-analysis, AOI
CRUD, monitors, events, and the toast/SSE systems are all verified. The four
things that *looked* broken tonight were **one root cause each**, all fixed
this pass — none were a button that "does nothing" by design.

## Live backend verification (real requests, this stack)

| Surface | Result |
|---|---|
| Dev-token + tiler-token auth | PASS |
| `GET /aois`, `GET /aois/{id}` | PASS (200) |
| `POST /aois` (create) → `DELETE` (archive) | PASS (201 → 204) |
| STAC search (Central Valley, 24-mo window) | PASS — 335 scenes |
| Full click-AOI → auto-search → auto-pick → **true-color tile renders** | PASS — real 256×256 JPEG, HTTP 200 |
| NDVI tilejson for the auto-picked scene | PASS (200) |
| **Run analysis** end-to-end | PASS — pending→running→**done in 30s**, real stats (4.95% changed) |
| `GET /analyses`, `GET /events`, `GET /detections` | PASS (200) |
| `POST /monitors` (create) → `DELETE` (deactivate) | PASS |

## UI interaction audit (code-verified wiring)

- **ModeSwitcher** (Explore/Analyze/Monitor) → `setMode`; drives scrubber +
  right panel. Correct.
- **CommandBar** — coord parse (N/S/E/W in any order), AOI name match, ⌘K
  focus, Enter jumps to top match, Escape clears. `requestFlyTo` wired.
  Correct. (Coordinate jump moves the *camera only* — it never loads
  imagery, by design: nothing searches scenes around a bare point. The
  on-map "No imagery loaded" hint now explains this.)
- **AOIPanel** — DRAW/SAVE/CANCEL, row-click select+fly, archive ×, SAVE AS
  MONITOR, freshly-drawn AOI now auto-selects, over-size AOI now rejected
  with a clear message. Correct.
- **LayersControl** — True Color/NDVI/Change are mutually exclusive (toggle
  semantics confirmed in the store), each with its own opacity slider;
  Detections is an independent vector toggle. Correct.
- **TemporalScrubber** — date range + SEARCH, SINGLE/BEFORE-AFTER toggle,
  scene-tick pick, auto-search-on-select, auto-pick, RUN ANALYSIS (guards on
  two distinct dates). Correct.
- **ResultsFeed** — result row → inspector + sets active analysis + flies to
  its AOI; detection/event rows → inspector. Correct.
- **MonitorPanel** — schedule presets, cron field, threshold, baseline date,
  CREATE, deactivate switch, row→inspector. Correct.
- **Inspector** — per-kind detail render, close ×, event→VIEW ANALYSIS.
  Correct.
- **Toast** — auto-dismiss (12s), manual close, de-dupe by id, max 3.
  Correct.
- **SSE event stream** — single shared connection, bearer-auth via manual
  fetch/ReadableStream, `LIVE SSE·OK` reflects real state; alert watcher
  toasts only genuinely-fresh events. Correct.

## The four things that looked broken → their real single causes (all fixed)

1. **"Infinite loading"** — the imagery search had no item cap and no
   network timeout; a continent-sized AOI matched millions of scenes and
   never returned. Fixed: capped at 200 items + 30s timeout (verified live —
   the exact hanging AOI now returns in 13s), plus a 60s frontend request
   timeout so any future hang becomes a visible error, not a silent spinner.
2. **"Run analysis isn't doing anything"** — not a pipeline bug (it completes
   in 30s, proven above); it no-ops only with no valid AOI+dates selected.
   The giant/archived AOIs left nothing usable selected. A correctly-sized
   Central Valley AOI has been restored on this install to click.
3. **Backend validations "not working"** (giant AOI accepted, identical
   dates accepted, bad cron accepted) — the running API image was built
   ~18h *before* those validations were committed. The old `.images-loaded`
   marker was version-blind, so app upgrades never refreshed backend images.
   Fixed: the marker now records the app version; a mismatch re-pulls, and
   boot.rs now recreates containers on a real image change (podman-compose
   won't reliably recreate a same-tagged image on its own).
4. **"Can't zoom out while drawing"** — `dragPan` was still disabled during
   drawing (a leftover from the pre-interleaved-mode era when clicks were
   eaten). Re-enabled; only double-click-zoom stays off (it finishes the
   ring). Being locked to the initial view is also how a continent-sized AOI
   gets drawn by accident in the first place.

## Verified green

`launcher-core` 34/34 · `apps/api` 34/34 · `tsc --noEmit` clean · production
build clean · live imagery render · live run-analysis. Shipping as the next
tagged release.
