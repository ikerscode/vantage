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

use crate::state::LauncherState;

const HEALTH_GATE_TIMEOUT: Duration = Duration::from_secs(180);
const POLL_INTERVAL: Duration = Duration::from_millis(1500);

#[derive(Serialize, Clone)]
struct BootProgress {
    message: String,
}

#[derive(Serialize, Clone)]
struct BootFailed {
    message: String,
}

fn emit_progress(app: &AppHandle, message: impl Into<String>) {
    let message = message.into();
    log::info!("{message}");
    let _ = app.emit("vantage://boot-progress", BootProgress { message });
}

fn emit_failed(app: &AppHandle, message: impl Into<String>) {
    let message = message.into();
    log::error!("{message}");
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

    emit_progress(&app, "loading offline images…");
    // Checked in order (BRIEF v1.6 — see OFFLINE_BUNDLE_REPORT.md): the
    // bundled-resource path is kept as a candidate in case a future build
    // ever does embed the tarball, but the real path today is the
    // operator-provided one — the tarball is ~6.6 GiB, over 3x GitHub's
    // hard 2 GiB release-asset cap, so it ships as a separate chunked
    // download the operator reassembles into VANTAGE's data directory
    // (see docs/AIRGAP.md), not inside the installer.
    let tarball_candidates = vec![
        resource_dir.join("infra").join("vantage-images-1.0.0.tar"),
        data_dir.join("vantage-images-1.0.0.tar"),
    ];
    match images::ensure_images_loaded(&runtime, &tarball_candidates, &data_dir) {
        Ok(true) => emit_progress(&app, "loaded images from the offline bundle"),
        Ok(false) => emit_progress(
            &app,
            "no offline image bundle found — see docs/AIRGAP.md to download one \
             (required for a fully offline install; these images are never pulled \
             from a registry)",
        ),
        Err(e) => emit_progress(&app, format!("warning: couldn't load offline images: {e}")),
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
        Ok(output) if !output.status.success() => {
            emit_failed(
                &app,
                format!("compose up failed:\n{}", String::from_utf8_lossy(&output.stderr)),
            );
            return;
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
        let _ = window.navigate("index.html".parse().expect("static literal is a valid URL"));
    }
}
