#!/usr/bin/env bash
#
# VANTAGE — one-shot source install/run for Ubuntu (podman).
#
# Brings up the full backend container stack and the web UI from source, with
# the snap-podman storage workaround baked in. Idempotent: safe to re-run.
#
# Usage:
#   ./install.sh                # full stack + UI (UI runs in the foreground)
#   ./install.sh --rebuild      # force-rebuild the backend images first
#   ./install.sh --backend-only # bring up the backend, don't start the UI
#
# Troubleshooting — api stuck "unhealthy" with a Postgres auth error
# ("password authentication failed" / "no password supplied"):
#   The DB data volume was initialized with different secrets than the current
#   infra/.env (e.g. secrets were regenerated after the volume already existed,
#   or infra/.env is incomplete). Postgres only runs its init/role scripts on a
#   FRESH volume, so the roles in the volume no longer match. Regenerate secrets
#   consistently and re-initialize the volume — DESTRUCTIVE, wipes the dev DB:
#       python3 scripts/generate_dev_secrets.py          # renders infra/.env + db-init together
#       podman-compose -f infra/docker-compose.yml down -v   # drops the DB/MinIO volumes
#       ./install.sh
#   (Skip this on a fresh machine — it only affects re-inits over a stale volume.)
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

log()  { printf '\033[36m[vantage]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[vantage] WARN:\033[0m %s\n' "$*"; }
die()  { printf '\033[31m[vantage] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

REBUILD=0
START_UI=1
for arg in "$@"; do
  case "$arg" in
    --rebuild) REBUILD=1 ;;
    --backend-only) START_UI=0 ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $arg (see --help)" ;;
  esac
done

# --- snap-podman workaround ------------------------------------------------
# The bug we hit repeatedly: a snap-confined shell (e.g. the VS Code snap) sets
# XDG_DATA_HOME to a per-revision path like ~/snap/code/249/.local/share, and
# podman's storage DB stops matching it after the snap auto-updates. Pin
# podman's storage to the stable, non-snap location instead.
if [[ "${XDG_DATA_HOME:-}" == *"/snap/"* ]]; then
  export XDG_DATA_HOME="$HOME/.local/share"
  log "snap-confined shell detected — pinned XDG_DATA_HOME=$XDG_DATA_HOME for stable podman storage"
fi

# --- prerequisites ---------------------------------------------------------
need_apt=()
command -v podman >/dev/null 2>&1 || need_apt+=(podman)
command -v curl   >/dev/null 2>&1 || need_apt+=(curl)
command -v node   >/dev/null 2>&1 || need_apt+=(nodejs)
command -v npm    >/dev/null 2>&1 || need_apt+=(npm)

# Pick a compose provider (prefer the standalone podman-compose).
COMPOSE=""
if command -v podman-compose >/dev/null 2>&1; then
  COMPOSE="podman-compose"
elif podman compose version >/dev/null 2>&1; then
  COMPOSE="podman compose"
else
  need_apt+=(podman-compose)
  COMPOSE="podman-compose"
fi

if (( ${#need_apt[@]} > 0 )); then
  log "installing missing prerequisites via apt: ${need_apt[*]}"
  sudo apt-get update -y
  sudo apt-get install -y "${need_apt[@]}"
  command -v podman-compose >/dev/null 2>&1 && COMPOSE="podman-compose"
fi

node_major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
if (( node_major < 18 )); then
  warn "Node $(node -v 2>/dev/null || echo '?') is older than v18 — the frontend build wants Node >=18."
  warn "Install a newer Node (nvm or NodeSource) if 'npm run dev' fails. The backend is unaffected."
fi
log "compose provider: $COMPOSE"

# --- backend env -----------------------------------------------------------
if [[ ! -f infra/.env ]]; then
  cp infra/.env.example infra/.env
  log "created infra/.env from infra/.env.example (dev-default secrets)"
fi

# --- backend stack (idempotent) --------------------------------------------
build_flag=""
(( REBUILD == 1 )) && build_flag="--build"
log "starting backend stack ${build_flag:+(forcing image rebuild) }— the first run builds images and can take several minutes…"
# shellcheck disable=SC2086
$COMPOSE -f infra/docker-compose.yml up -d $build_flag

# --- wait for API health ---------------------------------------------------
log "waiting for the API to report healthy…"
healthy=0
for _ in $(seq 1 60); do
  if curl -fsS --max-time 3 http://localhost:8000/api/health >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 3
done
if [[ "$healthy" != 1 ]]; then
  die "API never became healthy. Inspect logs with:  $COMPOSE -f infra/docker-compose.yml logs api"
fi
log "API healthy at http://localhost:8000"

# --- frontend --------------------------------------------------------------
if [[ ! -f apps/web/.env ]]; then
  printf 'VITE_API_BASE_URL=http://localhost:8000\nVITE_TILER_BASE_URL=http://localhost:8001\n' > apps/web/.env
  log "created apps/web/.env pointing at the local backend"
fi
log "installing frontend dependencies…"
( cd apps/web && npm install --no-fund --no-audit )

if (( START_UI == 0 )); then
  log "backend is up. Start the UI yourself with:  cd apps/web && npm run dev"
  exit 0
fi

log "backend is up. Launching the UI at http://localhost:5173 …"
log "(Ctrl+C stops the UI; the backend keeps running. Stop it with: $COMPOSE -f infra/docker-compose.yml down)"
cd apps/web
exec npm run dev
