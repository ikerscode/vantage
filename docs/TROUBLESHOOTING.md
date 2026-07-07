# Troubleshooting

## The app says "No container runtime found"

Install Docker or Podman, then relaunch VANTAGE:

- **Linux**: `sudo apt install podman` (Debian/Ubuntu) or your distro's equivalent. Docker works too if you already have it.
- **macOS**: install [Docker Desktop](https://www.docker.com/products/docker-desktop/) or `brew install podman`.
- **Windows**: install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (needs WSL2, which its installer sets up for you).

The launcher checks for `podman compose` / `podman-compose` / `docker compose` specifically, not just the base runtime — make sure whichever one you installed includes its compose plugin (Docker Desktop and recent Podman both do by default).

## It's stuck on the splash screen

The splash shows the actual step it's on ("starting database…", "loading tiler…", service-by-service health status) — that's not decorative, it's telling you what's slow or stuck. If it sits on one line for more than ~2 minutes:

1. Tray menu → **Export Support Bundle…** — this collects every service's logs into a local folder (never uploaded anywhere — see `PACKAGE_REPORT.md` §10) and opens it for you.
2. Look at the log file named after whichever service the splash was stuck on.
3. Common causes: a port already in use by something else (the launcher tries to pick a free one automatically, but a very unusual setup could still collide — check `${data_dir}/config/.env` for the actual `VANTAGE_*_PORT` values it landed on), or a genuinely slow first-run image load on a spinning disk.

After 3 minutes the launcher gives up waiting and shows an explicit failure instead of hanging forever — that message plus the support bundle is what to include if you're asking someone else for help.

## The demo AOI shows no imagery

This should not happen with the default (offline) imagery mode — the demo scenes ship inside the installer. If it does:

1. Check `${data_dir}/config/.env`'s `IMAGERY_SOURCE` — should be `static_catalog` for the default offline experience.
2. Check `${data_dir}/demo-data/manifest.json` exists and `${data_dir}/demo-data/2025-06-19/` (etc.) has `.tif` files in it — if that directory is empty, the bundled-resource copy step failed (support bundle will show a warning about it in the launcher's own log, not a service log).
3. If you switched to `IMAGERY_SOURCE=earth_search` (online mode) and have no internet, that's expected — switch back or reconnect.

## Port conflicts

The launcher probes each default port (8000 for the API, 8001 for the tiler, 5432 for Postgres) and picks a different free one automatically if something else already owns it — you shouldn't need to do anything. If you want to know which ports it actually landed on: check `${data_dir}/config/.env` (`VANTAGE_API_PORT`, `VANTAGE_TILER_PORT`, `VANTAGE_DB_PORT`).

## Exporting a support bundle

Tray menu → **Export Support Bundle…**. This is **local-only** — it writes a folder to `${data_dir}/support-bundles/<timestamp>/` containing every service's logs plus a manifest with the app version, and opens that folder in your file manager. Nothing is uploaded automatically; attach it to an email/ticket yourself if asked.

## Clean restart

Tray menu → **Restart** — runs a real `compose down` then `compose up`, not just a process kill, so ports are cleanly released first.

## Uninstall didn't remove my data

That's intentional — see INSTALL.md's uninstall section. The OS-level uninstaller removes the app; your imagery/analyses/config live separately in the data directory and need a confirmed, explicit removal (the app's own uninstall flow prompts for this, or delete the directory by hand — see the path table in `INSTALL.md`).

## Where things actually are, if you want to look yourself

| What | Where |
|---|---|
| Config + secrets | `${data_dir}/config/.env` |
| Database files | `${data_dir}/postgres/` |
| Object store (imagery outputs, chips) | `${data_dir}/minio/` |
| Bundled demo imagery | `${data_dir}/demo-data/` |
| Service logs (raw, not the curated support bundle) | `${data_dir}/logs/` |
| Support bundles | `${data_dir}/support-bundles/` |

(`${data_dir}` per OS: see the table in `INSTALL.md`.)
