//! Orchestrates bringing the stack up and health-gating the splash screen
//! (BRIEF v1.3 §2, §11). All the actual logic lives in
//! vantage_launcher_core, which is unit-tested independent of Tauri — this
//! module is just the glue that drives it and reports progress to the
//! splash window (apps/web/public/splash.html) via Tauri events.

use std::path::PathBuf;
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager};
use vantage_launcher_core::{compose, health, images, runtime_detect, secrets, seed};

use crate::state::{BootStatus, LauncherState};

// Found for real in CI (BRIEF v1.6's clean-machine acceptance test): a
// cold boot of the full stack (db -> pgstac-migrate -> api-migrate ->
// minio-init -> api/tiler) on a modest machine can genuinely take longer
// than 3 minutes — the previous value was never tested against a real
// cold start (no prior brief had actually launched the packaged app).
// This is real first-boot cost, not a bug to paper over with a longer
// number alone: worth a real look if it keeps needing more than this in
// practice, but 3 minutes was demonstrably too tight even once.
const HEALTH_GATE_TIMEOUT: Duration = Duration::from_secs(420);
const POLL_INTERVAL: Duration = Duration::from_millis(1500);

#[derive(Serialize, Clone)]
struct BootProgress {
    message: String,
}

#[derive(Serialize, Clone)]
struct BootFailed {
    message: String,
}

// Recording into LauncherState.last_status (not just emitting the Tauri
// event) is what lets a late-loading splash page catch up via
// get_boot_status instead of silently missing a fast failure — see
// state.rs's BootStatus doc comment.
fn record_status(app: &AppHandle, status: BootStatus) {
    let state = app.state::<LauncherState>();
    *state.last_status.lock().expect("last_status mutex poisoned") = status;
}

fn emit_progress(app: &AppHandle, message: impl Into<String>) {
    let message = message.into();
    log::info!("{message}");
    record_status(app, BootStatus::Progress { message: message.clone() });
    let _ = app.emit("vantage://boot-progress", BootProgress { message });
}

fn emit_failed(app: &AppHandle, message: impl Into<String>) {
    let message = message.into();
    log::error!("{message}");
    record_status(app, BootStatus::Failed { message: message.clone() });
    let _ = app.emit("vantage://boot-failed", BootFailed { message });
}

/// Runs on a background thread from main.rs's setup hook — everything here
/// is blocking I/O (subprocess calls, HTTP polls), deliberately not async,
/// to keep this module (and launcher-core underneath it) trivially
/// testable without pulling in an async runtime.
pub fn run(app: AppHandle, data_dir: PathBuf, api_port: u16, tiler_port: u16, db_port: u16) {
    emit_progress(&app, "checking for a container runtime…");
    let Some(runtime) = runtime_detect::detect() else {
        emit_failed(
            &app,
            "No container runtime found. VANTAGE needs Podman or Docker installed and \
             running — see INSTALL.md for your OS's one-line install command, then relaunch.",
        );
        return;
    };
    emit_progress(&app, format!("using {runtime:?}"));

    emit_progress(&app, "preparing configuration…");
    let opts = secrets::DeploymentOptions {
        data_dir: data_dir.clone(),
        api_port,
        tiler_port,
        db_port,
        api_image: "vantage-api:1.0.0".into(),
        tiler_image: "vantage-tiler:1.0.0".into(),
        inference_image: "vantage-inference:1.0.0".into(),
        inference_device: "cpu".into(),
    };
    let config_paths = match secrets::ensure_config(&opts) {
        Ok(p) => p,
        Err(e) => {
            emit_failed(&app, format!("couldn't write config to {}: {e}", data_dir.display()));
            return;
        }
    };
    if config_paths.freshly_generated {
        emit_progress(&app, "generated new per-install secrets");
    }

    let resource_dir = app.path().resource_dir().expect("resource dir must resolve inside a bundled app");
    let compose_file = resource_dir.join("infra").join("docker-compose.prod.yml");

    emit_progress(&app, "preparing demo imagery…");
    match seed::ensure_demo_data(&resource_dir.join("infra").join("demo-data"), &data_dir) {
        Ok(true) => emit_progress(&app, "copied bundled demo imagery"),
        Ok(false) => {}
        Err(e) => {
            // Not fatal — offline demo mode just won't have imagery to show;
            // online/internal imagery modes don't depend on this at all.
            emit_progress(&app, format!("warning: couldn't copy demo data: {e}"));
        }
    }

    emit_progress(&app, "getting container images…");
    // Checked in order (BRIEF v1.6's air-gap bundle, BRIEF v1.7's
    // thin/online path — see OFFLINE_BUNDLE_REPORT.md and
    // PACKAGING_V2_REPORT.md): the bundled-resource path is kept as a
    // candidate in case a future build ever does embed the tarball; the
    // operator-provided data-dir path is the real air-gap path today (a
    // separate chunked download reassembled into VANTAGE's data directory
    // — see docs/AIRGAP.md, required for genuinely offline operation). If
    // neither has a tarball, ensure_images_loaded falls through to a
    // registry pull — the thin/online-installer path most users should
    // actually hit. If THAT also fails (no bundle, no network), that's a
    // real unrecoverable state, surfaced as a hard failure here rather
    // than a warning that leaves `compose up` to fail later with a
    // cryptic "pull access denied" (these images were never on any
    // registry before BRIEF v1.7 — see images.rs's own module docs).
    let tarball_candidates = vec![
        resource_dir.join("infra").join("vantage-images-1.0.0.tar"),
        data_dir.join("vantage-images-1.0.0.tar"),
    ];
    match images::ensure_images_loaded(&runtime, &tarball_candidates, &data_dir) {
        Ok(images::ImageSource::AlreadyLoaded) => {}
        Ok(images::ImageSource::Tarball) => emit_progress(&app, "loaded images from the offline bundle"),
        Ok(images::ImageSource::Registry) => emit_progress(&app, "pulled images from the container registry"),
        Err(e) => {
            emit_failed(&app, format!("couldn't get the required container images: {e}"));
            return;
        }
    }

    emit_progress(&app, "starting database, object store, and services…");
    let runner = compose::ComposeRunner::new(runtime, compose_file, config_paths.env_file.clone());
    // Stashed in shared state BEFORE `up()` — even a failed/stuck boot
    // should leave the tray's "View Logs"/"Restart" usable for
    // troubleshooting, not just a successful one.
    {
        let state = app.state::<LauncherState>();
        *state.runner.lock().expect("runner mutex poisoned") = Some(runner);
    }
    let state = app.state::<LauncherState>();
    let runner_guard = state.runner.lock().expect("runner mutex poisoned");
    let runner = runner_guard.as_ref().expect("just set above");

    match runner.up() {
        // BRIEF v1.8, found for real on a user's Podman install: a non-zero
        // exit here does NOT necessarily mean the stack is unusable — some
        // compose providers (confirmed: podman-compose 1.5.0, the standalone
        // Python tool podman delegates to when no native compose plugin is
        // present) have known bugs tracking `condition:
        // service_completed_successfully` dependencies across one-shot
        // containers (pgstac-migrate/minio-init/api-migrate/demo-seed here),
        // causing `up -d` to report a dependency-tracking error even though
        // every service that matters came up and is genuinely healthy. The
        // health-gate poll below is the actual source of truth (this
        // function's own long-standing design, per the comment on
        // compose.rs's `up()`) — so a failed exit status is logged and
        // surfaced as a warning, not treated as fatal on its own. Only the
        // health-gate timeout below can still fail the boot for real.
        Ok(output) if !output.status.success() => {
            emit_progress(
                &app,
                format!(
                    "warning: compose reported an error (continuing to check real service health): {}",
                    String::from_utf8_lossy(&output.stderr)
                ),
            );
        }
        Err(e) => {
            emit_failed(&app, format!("couldn't run compose: {e}"));
            return;
        }
        Ok(_) => {}
    }
    drop(runner_guard);

    emit_progress(&app, "waiting for services to report healthy…");
    let targets = health::default_targets(api_port, tiler_port);
    let started = Instant::now();
    loop {
        let results = health::poll_once(&targets);
        for (name, status) in &results {
            emit_progress(&app, format!("{name}: {status:?}"));
        }
        if health::all_healthy(&results) {
            break;
        }
        if started.elapsed() > HEALTH_GATE_TIMEOUT {
            emit_failed(
                &app,
                "services didn't become healthy within 3 minutes — open the logs \
                 (tray menu → View Logs) to see what's stuck.",
            );
            return;
        }
        std::thread::sleep(POLL_INTERVAL);
    }

    // No filesystem write needed here — the api/tiler ports were already
    // baked into the window's initialization_script back in main.rs, before
    // this window ever loaded splash.html. See
    // vantage_launcher_core::config::FrontendRuntimeConfig::to_init_script.
    emit_progress(&app, "ready");
    if let Some(window) = app.get_webview_window("main") {
        // BRIEF v1.8, found for real on a user's machine: "index.html" is a
        // relative path, not an absolute URL, and `str::parse::<Url>()`
        // requires an absolute URL with a scheme+host — it has no base to
        // resolve a bare relative path against. The `.expect(...)` here
        // always panicked, silently killing this background thread right
        // at the final step of an otherwise fully successful boot (health
        // checks passing, "ready" already logged) — the app just sat on
        // the splash screen forever with no further progress possible,
        // since the thread that would drive it had already died. Fixed by
        // resolving against the window's own CURRENT url (whatever scheme
        // Tauri's webview is actually using — tauri://localhost,
        // http://tauri.localhost, etc. — varies by platform, so this must
        // not be hardcoded) via Url::join, which is what relative-URL
        // resolution actually requires.
        match window.url().and_then(|current| {
            current
                .join("index.html")
                .map_err(|e| tauri::Error::InvalidUrl(e))
        }) {
            Ok(target) => {
                if let Err(e) = window.navigate(target) {
                    emit_failed(&app, format!("couldn't navigate to the app UI: {e}"));
                }
            }
            Err(e) => emit_failed(&app, format!("couldn't resolve the app UI's URL: {e}")),
        }
    }
}
