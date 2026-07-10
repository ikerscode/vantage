# VANTAGE User Manual

This covers using the app once it's running — drawing areas of interest,
reading imagery, running change-detection, and setting up monitors. If
you haven't installed it yet, see [INSTALL.md](../INSTALL.md) first. If
something's actually broken (won't launch, stuck on splash, black map with
no imagery ever appearing), see [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md)
instead — this manual assumes a working install.

## What you're looking at

VANTAGE is an imagery **analysis** workbench: it reports what's present and
what changed between two dates over an area you define. It is deliberately
not styled like a targeting system — no crosshairs, no lock-on markers, no
red "threat" boxes. One accent color (cyan) marks selection and chrome;
detected objects are drawn as neutral outline boxes, with opacity scaled by
the model's confidence, not by any notion of severity. See
[COMPLIANCE.md](../COMPLIANCE.md) for the fuller statement of what this tool
is and isn't for.

The whole app is one full-bleed dark map with panels floating over it —
there's no separate settings page or second window to find.

```
┌──────────────────────────────────────────────────────────────────┐
│  [ CUR  UTC  AOI/ALERT  SCENE  LIVE  scale  version ]  ← status strip
│              [ EXPLORE | ANALYZE | MONITOR ]  ← mode switcher       │
│              [ 🔍  Jump to coordinates or AOI…  ⌘K ]  ← command bar │
│  ┌─────────────┐                              ┌─────────────────┐  │
│  │ Areas of    │                              │ Inspector /     │  │
│  │ Interest    │        (the map itself)       │ Monitors        │  │
│  ├─────────────┤                              ├─────────────────┤  │
│  │ Layers      │                              │ Results / Events│  │
│  └─────────────┘                              └─────────────────┘  │
│                    [ Timeline / scrubber ]  ← bottom                │
└──────────────────────────────────────────────────────────────────┘
```

- **Left**: Areas of Interest (AOIs you've drawn) and Layers (imagery/detection
  visibility).
- **Right**: Inspector (details of whatever you last clicked) in Explore/Analyze
  mode, or the Monitors list in Monitor mode — plus the Results/Events feed
  underneath either way.
- **Bottom**: the Timeline (temporal scrubber) — where you pick which scene(s)
  you're looking at.
- **Top**: the status strip, mode switcher, and command bar.

## The three modes

The mode switcher (top center) changes what the right-hand panel and the
timeline are *for* — everything else (map, AOIs, layers) stays the same.

| Mode | Timeline shows | Right panel shows | Use it to… |
|---|---|---|---|
| **Explore** | Single-date scrubber — pick one scene | Inspector | Browse available imagery over an AOI, one date at a time |
| **Analyze** | Before/after scrubber — pick two scenes, then RUN ANALYSIS | Inspector | Run an on-demand change-detection between two dates |
| **Monitor** | A watch history (dots = past analyses, NOW marker) | Monitors list | Set up a recurring scheduled check on an AOI, and see live alerts |

Switching modes doesn't lose your date picks — the scrubber remembers a
before/after pair and a single date independently and just shows whichever
one is relevant to the current mode.

## Step by step

### 1. Find a place

Click the command bar (top center) or press **⌘K** / **Ctrl+K** from
anywhere. Type either:
- **Coordinates** — `34.92, -44.10`, `34.92 -44.10`, or with compass suffixes
  in either order, e.g. `44.10°E 34.92°N`. Press **Enter** to fly there.
- **An AOI name** (partial match) — selects it and flies to its centroid.

Press **Escape** to clear and unfocus.

There's no place-name/address search (that would mean an internet-dependent
geocoding service, which conflicts with VANTAGE running fully offline — see
the architecture notes in the repo's `CLAUDE.md`). Coordinates and your own
AOIs are the two ways to navigate.

### 2. Draw an Area of Interest (AOI)

In the **Areas of Interest** panel (left), click **DRAW NEW AOI**. The
button label changes to *"DRAWING… CLICK TO ADD VERTEX"* — click points on
the map to place a polygon, then double-click to close the ring. A name
field appears once you've drawn something: type a name and click **SAVE**
(or **CANCEL** to discard). While drawing, map panning and double-click-zoom
are intentionally disabled so your clicks place vertices instead of moving
the map.

AOI polygons are validated before they're saved: they must be a simple
(non-self-intersecting) shape with real area, and implausibly large
polygons are rejected (the realistic way that happens is an accidental
longitude/latitude swap, not a genuinely huge AOI — if you actually need
one that big, split it into smaller AOIs).

Click any saved AOI in the list (or its outline on the map) to select it —
selection drives everything downstream: the timeline searches imagery for
that AOI, and Analyze/Monitor act on whichever AOI is selected. The **×** on
a row archives that AOI. On first launch, if nothing is selected yet,
VANTAGE auto-selects and flies to your first AOI so the map never opens on
a location with nothing loaded — this only happens once and never overrides
a choice you've made yourself.

### 3. Browse imagery (Explore mode)

With an AOI selected, the **Timeline** at the bottom searches for available
scenes automatically (you can also set a custom date range and click
**SEARCH**). Each tick on the axis is a scene; taller/brighter ticks are
lower cloud cover. Click a tick to view that scene — it also auto-picks the
most recent scene the first time results come in, so there's always
something on the map without a manual click.

Turn on a raster layer in the **Layers** panel (left) to actually see it:
**True Color**, **NDVI**, or **Change** — these three are mutually exclusive
(switching to one turns off the others) since they're different renderings
of the same underlying imagery, not things you'd overlay together. Each has
its own opacity slider.

### 4. Run a change-detection analysis (Analyze mode)

Switch to **Analyze**. The timeline now shows a before/after picker — click
one scene tick for the "before" date, then another for "after" (the
handles are labeled and color-coded: plain for before, accent for after).
Click **RUN ANALYSIS**. While it runs, a job card appears in the **Results**
panel with an indeterminate progress bar; once done, it appears as a row
you can click to inspect (changed-pixel count, percent changed, and the
threshold used). Turn on the **Change** layer to see the change map
rendered on top of the imagery.

Analyses require two genuinely different dates — the two scrubber handles
can't land on the same scene, since diffing a scene against itself would
always silently report "no change."

### 5. Inspect anything

Click any AOI, analysis result, detection box, monitor, or event, and the
**Inspector** (right panel, Explore/Analyze modes) shows its details —
status, dates, threshold, changed-pixel stats, or (for a detection) its
confidence score as a filled bar. Click the **×** in the Inspector's header
to close it.

### 6. Set up a Monitor

Switch to **Monitor** mode (or click **SAVE AS MONITOR** at the bottom of
the AOI panel, which jumps you there with the AOI already selected). Pick a
schedule — **HOURLY** / **DAILY** / **WEEKLY** presets, or type your own
5-field cron expression directly. Optionally set an NDVI-diff threshold
(default 0.2 if left blank) and a fixed baseline date to always compare
against (otherwise it compares each new scene against the previous one it
saw — a rolling comparison). Click **CREATE MONITOR**.

Each monitor in the list shows a status dot:
- **WATCHING** (green) — active, no recent alert
- **ALERT** (red) — a change event landed for this monitor in the last 10
  minutes
- **PAUSED** (gray) — deactivated

Click the switch on a monitor row to deactivate it (reactivating an
existing monitor isn't supported yet — create a new one instead). Click a
monitor row itself to inspect its schedule, active state, and last-run
time.

### 7. Watch for alerts

Monitors run on the schedule you gave them (server-side, independent of
whether VANTAGE is open) and publish an **Event** whenever a change exceeds
the threshold. You'll see this three ways, live, without refreshing:
- A toast notification in the corner.
- The status strip's **AOI** segment is replaced by a pulsing **ALERT** chip
  naming the affected AOI (or monitor count, if more than one).
- In Monitor mode, the **Live Events** feed lists it immediately, highlighted
  while inside that 10-minute alert window.

The **LIVE** segment on the status strip shows whether the live-events
connection is actually up (`SSE·OK`) — if it says `SSE·DOWN`, alerts will
still show up once you reload, just not in real time.

## Status strip reference

Left to right: **CUR** (cursor lat/lon under your mouse) · **UTC** (live
clock, Zulu time) · **AOI** or **ALERT** (selected AOI name, or an alert chip
when one exists) · **SCENE** (currently viewed scene's timestamp and cloud
cover) · **LIVE** (event-stream connection state) · a scale bar and zoom
level · the app version (desktop build only).

## Things that might surprise you

- **The map has no basemap imagery of its own** — no streets, no terrain, just
  a dark void until you select an AOI and a scene. This is deliberate (see
  `CLAUDE.md`'s no-hosted-basemap rule), but it means "nothing selected yet"
  and "imagery failed to load" both look identical: solid black. If you see
  black, check the **SCENE** field on the status strip — if it says "—", pick
  a scene; if it shows a real date, check `docs/TROUBLESHOOTING.md`.
- **Raster layers are mutually exclusive.** Turning on NDVI turns off True
  Color, not layers you'd stack.
- **First AOI selection and its imagery search happen automatically once**,
  but only ever once per AOI, and never if you've already made your own
  choice — so if you deliberately deselect everything, VANTAGE won't force
  a re-selection back on you.
- **A monitor's "reactivate" switch is disabled once paused** — this is a
  known current limitation, not a bug; create a new monitor instead.

## See also

- [INSTALL.md](../INSTALL.md) — installing the app itself
- [docs/AIRGAP.md](AIRGAP.md) — fully offline / air-gapped deployment
- [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) — it launched but something's wrong
- [COMPLIANCE.md](../COMPLIANCE.md) — what this tool is (and isn't) for
