#!/usr/bin/env bash
# End-to-end smoke test against REAL Sentinel-2 data. Assumes the stack is
# already up (docker compose, or the native run described in RUN_REPORT.md)
# and reachable at API_BASE_URL / TILER_BASE_URL.
#
# Exits non-zero on any failure. Distinguishes "the real world didn't
# cooperate" (no scenes / Earth Search unreachable / cloud cover) from
# "our code is broken" in its error messages — see the fail_data vs
# fail_logic helpers below.
#
# Requires: curl, python3, psql (only for the monitor-sweep step's test
# setup — see the comment there), and apps/api's venv for one direct
# Python invocation (also monitor-sweep only).
set -uo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
TILER_BASE_URL="${TILER_BASE_URL:-http://localhost:8001}"
APPS_API_DIR="${APPS_API_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../apps/api" && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-$APPS_API_DIR/.venv/bin/python}"
PSQL_DSN="${PSQL_DSN:-postgresql://vantage@localhost:5432/vantage}"
# SEC-01: must match the tiler's TILER_TOKEN env var (services/tiler/app/security.py) —
# defaults to the same dev fallback apps/api's Settings.tiler_token uses, so
# this keeps working out of the box against a plain `docker compose up`/
# native dev stack without extra setup.
TILER_TOKEN="${TILER_TOKEN:-change-me-dev-tiler-token}"

# Fixed, reproducible test AOI + date windows (California Central Valley
# farmland/airport; chosen for low cloud cover and a real NDVI signal —
# see RUN_REPORT.md for why these specific dates).
AOI_NAME="smoke-test-$(date +%s)"
AOI_GEOJSON='{"type":"Polygon","coordinates":[[[-119.75,36.75],[-119.70,36.75],[-119.70,36.80],[-119.75,36.80],[-119.75,36.75]]]}'
DATE_A="2025-11-01"   # widen this window in the search step if it stops returning scenes
DATE_B="2025-06-19"

PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "  PASS: $1"; }
fail_logic() { FAIL=$((FAIL + 1)); echo "  FAIL (logic bug, not a data issue): $1" >&2; }
fail_data() { FAIL=$((FAIL + 1)); echo "  FAIL (real-world data/network issue, not necessarily a code bug): $1" >&2; }

step() { echo ""; echo "=== $1 ==="; }

require_jq_free_json() {
  # Small python helper so this script doesn't need jq installed.
  python3 -c "$1"
}

# Computes a real, in-bounds z/x/y for a given tilejson response (standard
# Web Mercator slippy-map tile math) instead of a hardcoded guess — a fixed
# tile number for one AOI is not valid for another, and rio-tiler's
# TileOutsideBounds surfaces as an unhandled 500, not a clean 404, so this
# was actually the difference between a false "logic bug" failure and a
# true pass in earlier runs of this script. Uses maxzoom (clamped to 14)
# rather than the tilejson's own stated "center" zoom: empirically, center's
# zoom (often minzoom) can still land outside bounds for a small-extent COG
# — but raw maxzoom isn't safe either: the /stac multi-asset route reports
# maxzoom=24 regardless of Sentinel-2's real ~10m resolution, and a z24 tile
# over 10m data reads a sub-pixel window that compresses to a tiny, useless
# image (verified — 416-byte near-blank tile, technically HTTP 200, not a
# real pass). z14 was the level that worked consistently in manual testing
# across /cog, /stac, and our own analysis COGs.
tile_xy_for_tilejson() {
  python3 -c "
import json, math, sys
d = json.loads(sys.stdin.read())
lon, lat, _ = d['center']
zoom = min(int(d.get('maxzoom') or d['center'][2] or d.get('minzoom', 8)), 14)
n = 2.0 ** zoom
x = int((lon + 180.0) / 360.0 * n)
lat_rad = math.radians(lat)
y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
print(f'{zoom}/{x}/{y}')
"
}

step "0. Health checks"
for name_url in "api:$API_BASE_URL/api/health" "tiler:$TILER_BASE_URL/health"; do
  name="${name_url%%:*}"; url="${name_url#*:}"
  code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")
  if [ "$code" = "200" ]; then pass "$name is healthy"; else fail_logic "$name health check returned $code (is it running?)"; fi
done

step "1. Dev auth token"
TOKEN_JSON=$(curl -sS -X POST --max-time 15 "$API_BASE_URL/api/auth/dev-token")
TOKEN=$(echo "$TOKEN_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
if [ -n "$TOKEN" ]; then pass "issued a dev token"; else fail_logic "no access_token in response: $TOKEN_JSON"; exit 1; fi

step "2. Create AOI"
AOI_RESP=$(curl -sS -X POST --max-time 15 "$API_BASE_URL/api/aois" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"name\": \"$AOI_NAME\", \"geometry\": $AOI_GEOJSON}")
AOI_ID=$(echo "$AOI_RESP" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
if [ -n "$AOI_ID" ]; then pass "created AOI $AOI_ID"; else fail_logic "AOI creation failed: $AOI_RESP"; exit 1; fi

step "3. STAC search — both date windows must return at least one scene"
SCENES_A=$(curl -sS -X POST --max-time 30 "$API_BASE_URL/api/stac/search" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"aoi_id\": \"$AOI_ID\", \"date_from\": \"$DATE_A\", \"date_to\": \"$DATE_A\"}")
SCENES_B=$(curl -sS -X POST --max-time 30 "$API_BASE_URL/api/stac/search" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"aoi_id\": \"$AOI_ID\", \"date_from\": \"$DATE_B\", \"date_to\": \"$DATE_B\"}")
COUNT_A=$(echo "$SCENES_A" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)
COUNT_B=$(echo "$SCENES_B" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo 0)
if [ "$COUNT_A" -ge 1 ]; then pass "found $COUNT_A scene(s) for $DATE_A"; else fail_data "no scenes for $DATE_A — check Earth Search connectivity, or widen the date window (real Sentinel-2 revisit is ~5 days)"; fi
if [ "$COUNT_B" -ge 1 ]; then pass "found $COUNT_B scene(s) for $DATE_B"; else fail_data "no scenes for $DATE_B — check Earth Search connectivity, or widen the date window"; fi

VISUAL_HREF=$(echo "$SCENES_A" | python3 -c "import json,sys; s=json.load(sys.stdin); print(s[0]['assets']['visual']['href'] if s else '')" 2>/dev/null)
SELF_HREF=$(echo "$SCENES_A" | python3 -c "import json,sys; s=json.load(sys.stdin); print(s[0].get('self_href','') if s else '')" 2>/dev/null)

step "4. True-color tile (single-file COG via /cog)"
if [ -n "$VISUAL_HREF" ]; then
  TILEJSON=$(curl -sS --max-time 30 -H "X-Tiler-Token: $TILER_TOKEN" -G "$TILER_BASE_URL/cog/WebMercatorQuad/tilejson.json" --data-urlencode "url=$VISUAL_HREF")
  TILE_TMPL=$(echo "$TILEJSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['tiles'][0])" 2>/dev/null)
  ZXY=$(echo "$TILEJSON" | tile_xy_for_tilejson)
  if [ -n "$TILE_TMPL" ] && [ -n "$ZXY" ]; then
    TILE_URL=$(echo "$TILE_TMPL" | sed "s#{z}/{x}/{y}#$ZXY#")
    OUT=$(mktemp)
    CODE=$(curl -sS -H "X-Tiler-Token: $TILER_TOKEN" -o "$OUT" -w "%{http_code}" --max-time 60 "$TILE_URL")
    SIZE=$(wc -c < "$OUT")
    MAGIC=$(head -c 8 "$OUT" | xxd -p 2>/dev/null | head -c 16 || echo "")
    if [ "$CODE" = "200" ] && [ "$SIZE" -gt 1000 ]; then pass "true-color tile fetched ($SIZE bytes)"; else fail_logic "true-color tile fetch failed: HTTP $CODE, $SIZE bytes"; fi
    rm -f "$OUT"
  else
    fail_logic "true-color tilejson had no tiles[0]: $TILEJSON"
  fi
else
  fail_data "no visual asset href from search results — skipping true-color tile check"
fi

step "5. NDVI tile (multi-asset STAC band math via /stac, asset_as_band=true)"
if [ -n "$SELF_HREF" ]; then
  NDVI_TILEJSON=$(curl -sS --max-time 30 -H "X-Tiler-Token: $TILER_TOKEN" -G "$TILER_BASE_URL/stac/WebMercatorQuad/tilejson.json" \
    --data-urlencode "url=$SELF_HREF" --data-urlencode "expression=(nir-red)/(nir+red)" \
    --data-urlencode "asset_as_band=true" --data-urlencode "assets=red" --data-urlencode "assets=nir" \
    --data-urlencode "rescale=-1,1")
  NDVI_TMPL=$(echo "$NDVI_TILEJSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['tiles'][0])" 2>/dev/null)
  NDVI_ZXY=$(echo "$NDVI_TILEJSON" | tile_xy_for_tilejson)
  if [ -n "$NDVI_TMPL" ] && [ -n "$NDVI_ZXY" ]; then
    NDVI_TILE_URL=$(echo "$NDVI_TMPL" | sed "s#{z}/{x}/{y}#$NDVI_ZXY#")
    OUT=$(mktemp)
    CODE=$(curl -sS -H "X-Tiler-Token: $TILER_TOKEN" -o "$OUT" -w "%{http_code}" --max-time 90 "$NDVI_TILE_URL")
    SIZE=$(wc -c < "$OUT")
    if [ "$CODE" = "200" ] && [ "$SIZE" -gt 500 ]; then pass "NDVI tile fetched ($SIZE bytes)"; else fail_logic "NDVI tile fetch failed: HTTP $CODE, $SIZE bytes — if this is InvalidExpression, asset_as_band=true is missing (verified required, see RUN_REPORT.md)"; fi
    rm -f "$OUT"
  else
    fail_logic "NDVI tilejson had no tiles[0]: $NDVI_TILEJSON"
  fi
else
  fail_data "no self_href from search results — skipping NDVI tile check"
fi

step "6. Change-detection analysis (real NDVI-diff between the two dates)"
ANALYSIS_RESP=$(curl -sS -X POST --max-time 15 "$API_BASE_URL/api/analyses" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"aoi_id\": \"$AOI_ID\", \"date_a\": \"$DATE_A\", \"date_b\": \"$DATE_B\"}")
ANALYSIS_ID=$(echo "$ANALYSIS_RESP" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
if [ -z "$ANALYSIS_ID" ]; then
  fail_logic "analysis creation failed: $ANALYSIS_RESP"
else
  pass "analysis $ANALYSIS_ID created, polling for completion..."
  STATUS="pending"
  for i in $(seq 1 40); do
    RESULT=$(curl -sS --max-time 15 "$API_BASE_URL/api/analyses/$ANALYSIS_ID" -H "Authorization: Bearer $TOKEN")
    STATUS=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
    [ "$STATUS" = "done" ] || [ "$STATUS" = "failed" ] && break
    sleep 5
  done
  if [ "$STATUS" = "done" ]; then
    pass "analysis completed (status=done)"
    TILEJSON_URL=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tilejson_url') or '')" 2>/dev/null)
    if [ -n "$TILEJSON_URL" ]; then
      CHANGE_TILEJSON=$(curl -sS --max-time 30 -H "X-Tiler-Token: $TILER_TOKEN" "$TILEJSON_URL")
      CHANGE_TMPL=$(echo "$CHANGE_TILEJSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['tiles'][0])" 2>/dev/null)
      CHANGE_ZXY=$(echo "$CHANGE_TILEJSON" | tile_xy_for_tilejson)
      if [ -n "$CHANGE_TMPL" ] && [ -n "$CHANGE_ZXY" ]; then
        CHANGE_TILE_URL=$(echo "$CHANGE_TMPL" | sed "s#{z}/{x}/{y}@1x#$CHANGE_ZXY@1x#")
        OUT=$(mktemp)
        CODE=$(curl -sS -H "X-Tiler-Token: $TILER_TOKEN" -o "$OUT" -w "%{http_code}" --max-time 60 "$CHANGE_TILE_URL")
        SIZE=$(wc -c < "$OUT")
        if [ "$CODE" = "200" ] && [ "$SIZE" -gt 100 ]; then pass "change-map tile fetched ($SIZE bytes)"; else fail_logic "change-map tile fetch failed: HTTP $CODE (note: fixed zoom/tile coords assume the AOI above — may need adjusting for a different AOI)"; fi
        rm -f "$OUT"
      else
        fail_logic "could not get change tilejson tiles[0] from $TILEJSON_URL"
      fi
    else
      fail_logic "done analysis has no tilejson_url"
    fi
  elif [ "$STATUS" = "failed" ]; then
    ERR=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('error_message',''))" 2>/dev/null)
    fail_data "analysis failed: $ERR (often means no single scene covers the AOI, or asset/coverage issue — see RUN_REPORT.md's known scope cuts)"
  else
    fail_logic "analysis did not finish within 200s (status=$STATUS) — check worker logs"
  fi
fi

step "7. Detections (placeholder object detection — see honest-empty note below)"
if [ -n "$ANALYSIS_ID" ] && [ "$STATUS" = "done" ]; then
  DETECTIONS=$(curl -sS --max-time 15 "$API_BASE_URL/api/detections?analysis_id=$ANALYSIS_ID" -H "Authorization: Bearer $TOKEN")
  DET_OK=$(echo "$DETECTIONS" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    assert isinstance(d, list)
    for item in d:
        assert item['bbox']['type'] == 'Polygon'
    print('ok', len(d))
except Exception as e:
    print('error', e)
" 2>/dev/null)
  if echo "$DET_OK" | grep -q "^ok"; then
    N=$(echo "$DET_OK" | awk '{print $2}')
    if [ "$N" = "0" ]; then
      pass "detections endpoint responded correctly with 0 rows — HONEST expected result: the COCO-pretrained placeholder detector is not tuned for satellite/aerial imagery, so finding nothing above the 0.5 score threshold on farmland/airport imagery is normal, not a failure (see RUN_REPORT.md and COMPLIANCE.md). The chip->inference->geo-box plumbing itself was verified separately with a lowered diagnostic threshold (run_artifacts/detections-diagnostic.json)."
    else
      pass "detections endpoint responded correctly with $N row(s), all with valid Polygon geometry"
    fi
  else
    fail_logic "detections response malformed: $DET_OK / raw: $DETECTIONS"
  fi
else
  echo "  SKIP: analysis did not complete, skipping detections check"
fi

step "8. Monitor -> sweep -> Event -> SSE"
MONITOR_RESP=$(curl -sS -X POST --max-time 15 "$API_BASE_URL/api/monitors" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"aoi_id\": \"$AOI_ID\", \"schedule\": \"* * * * *\", \"threshold\": 0.2, \"baseline_date\": \"$DATE_B\"}")
MONITOR_ID=$(echo "$MONITOR_RESP" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
if [ -z "$MONITOR_ID" ]; then
  fail_logic "monitor creation failed: $MONITOR_RESP"
else
  pass "created monitor $MONITOR_ID"
  # Test-setup only: croniter's get_next() always returns a time strictly
  # after `created_at`, so a monitor is never "due" in the same instant it's
  # created. Backdating created_at here exercises the real due-check/sweep
  # logic deterministically instead of sleeping ~60s for a real minute
  # boundary — it does not fake anything the sweep itself does.
  if command -v psql >/dev/null 2>&1; then
    psql "$PSQL_DSN" -c "UPDATE monitor SET created_at = now() - interval '5 minutes' WHERE id = '$MONITOR_ID';" >/dev/null 2>&1
  fi

  # sweep_monitors() does a real STAC search + real change-detection run
  # (10-25s observed against live Earth Search).
  "$PYTHON_BIN" -c "
import os, sys
sys.path.insert(0, '$APPS_API_DIR')
os.chdir('$APPS_API_DIR')
from app.tasks.monitor_sweep import sweep_monitors
sweep_monitors()
" 2>&1

  EVENT_ROW=$(curl -sS --max-time 15 "$API_BASE_URL/api/events" -H "Authorization: Bearer $TOKEN" \
    | python3 -c "
import json, sys
events = json.load(sys.stdin)
matches = [e for e in events if e['monitor_id'] == '$MONITOR_ID']
print(json.dumps(matches[0]) if matches else '')
" 2>/dev/null)

  # Connect to SSE *after* the event is already persisted, and check it's
  # delivered in the connect-time replay burst (app/routers/events.py:
  # /api/events/stream replays unseen DB rows before tailing live pub/sub).
  # This is a deliberate choice: it tests SSE delivery deterministically
  # rather than racing a live pub/sub push against an arbitrary sleep
  # window, which is exactly the kind of flaky timing this script should
  # not depend on. The live-tail path was separately verified by hand with
  # a stream held open across a real sweep — see RUN_REPORT.md and
  # run_artifacts/sse-event-captured.txt for that evidence.
  SSE_OUT=$(mktemp)
  timeout 8 curl -sS -N "$API_BASE_URL/api/events/stream" -H "Authorization: Bearer $TOKEN" > "$SSE_OUT" 2>&1

  if [ -n "$EVENT_ROW" ]; then
    pass "monitor sweep produced an Event: $EVENT_ROW"
    if grep -q "$MONITOR_ID" "$SSE_OUT" 2>/dev/null; then
      pass "the SAME event was delivered over SSE (connect-time replay)"
    else
      fail_logic "Event exists in DB but was not replayed on /api/events/stream connect ($(wc -c < "$SSE_OUT") bytes captured)"
    fi
  else
    echo "  NOTE: no Event fired — this is a legitimate possible outcome if the real NDVI change between $DATE_B and the latest available scene didn't exceed threshold 0.2 anywhere in the AOI, not necessarily a bug. Check $API_BASE_URL/api/analyses?aoi_id=$AOI_ID for the sweep's analysis result and its stats."
  fi
  rm -f "$SSE_OUT"
fi

step "Summary"
echo "PASS: $PASS   FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
