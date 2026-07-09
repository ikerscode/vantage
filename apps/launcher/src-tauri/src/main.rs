// SAFETY/SCOPE NOTE (see PACKAGE_REPORT.md "Environment reality"): this
// binary has NOT been compiled anywhere in this repo's history yet. The
// sandbox this was written in has no root access, so none of the Linux GTK
// stack Tauri's webview needs can be installed (libglib2.0-dev,
// libgtk-3-dev, libwebkit2gtk-4.1-dev, librsvg2-dev,
// libayatana-appindicator3-dev — see the INSTALL.md prerequisites list).
// `cargo check` gets past dependency compilation for everything else,
// INCLUDING dbus (see Cargo.toml's `dbus = { features = ["vendored"] }` —
// a real fix, not a workaround note: it builds libdbus from source instead
// of needing libdbus-1-dev), and fails only once it reaches glib-sys. Every
// non-GUI decision this file makes (secret generation, compose invocation,
// health-gating, port selection) is implemented in ../launcher-core, which
// DOES compile and has a real, passing test suite — see that crate's
// src/*.rs. Treat this file and boot.rs/state.rs as reviewed drafts:
// correct Tauri v2 API shapes to the best of available documentation, but
// unverified by a compiler past the GTK wall above. The first person who
// builds this on a machine with those five packages installed (or
// macOS/Windows, where the equivalent system webview is already present)
// should expect a short compile-fix pass, not a rewrite.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod boot;
mod state;

use std::sync::Mutex;

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_opener::OpenerExt;
use vantage_launcher_core::config::{default_data_dir, find_available_port, FrontendRuntimeConfig};
use vantage_launcher_core::secrets::read_rendered_value;
use vantage_launcher_core::support_bundle;

use crate::state::{BootStatus, LauncherState, SERVICES};

/// Lets splash.html pull the CURRENT boot status the moment it loads,
/// instead of only passively waiting for events it may have missed if
/// boot::run already progressed or failed before the page finished
/// loading — see state.rs's BootStatus doc comment for why this exists.
#[tauri::command]
fn get_boot_status(state: tauri::State<LauncherState>) -> BootStatus {
    state.last_status.lock().expect("last_status mutex poisoned").clone()
}

/// BRIEF v1.8, found for real on a user's machine: on any launch after the
/// first, secrets::ensure_config() reuses the existing `.env` untouched
/// (correct — regenerating it would orphan the already-provisioned Postgres
/// role passwords), but ports were always being freshly chosen via
/// find_available_port() regardless. That's fine when nothing is already
/// running, but if THIS app's own previous compose stack is still up
/// (e.g. the app was killed instead of quit through the tray, or was
/// simply launched twice), find_available_port(8000) correctly sees 8000
/// is taken (by that already-running stack) and picks a different port —
/// which the reused .env file, and therefore compose, knows nothing about.
/// The result: this launch health-checks and configures the frontend
/// against a port nothing is listening on, forever, while the actual
/// (healthy) services keep serving on the port baked into the untouched
/// .env. Fix: if a config already exists, read the ports actually baked
/// into it back out and use those — only pick fresh ports when there's no
/// existing config to be consistent with yet (first run).
fn resolve_ports(data_dir: &std::path::Path) -> (u16, u16, u16) {
    let env_path = data_dir.join("config").join(".env");
    // Real rendered key names (infra/.env.prod.template) — NOT the
    // template's internal {{API_PORT}}-style placeholder names, which are
    // a different, un-prefixed set only used during rendering itself.
    let persisted = ["VANTAGE_API_PORT", "VANTAGE_TILER_PORT", "VANTAGE_DB_PORT"]
        .map(|key| read_rendered_value(&env_path, key).and_then(|v| v.parse::<u16>().ok()));

    if let [Some(api), Some(tiler), Some(db)] = persisted {
        return (api, tiler, db);
    }

    (find_available_port(8000), find_available_port(8001), find_available_port(5432))
}

const APP_VERSION: &str = env!("CARGO_PKG_VERSION");

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        // Feeds both the app's own log output and the support-bundle export
        // (BRIEF v1.3 §11) — writes to the platform log dir alongside
        // stdout, so `log::info!`/`log::error!` calls in boot.rs land
        // somewhere a support engineer can actually find after the fact.
        .plugin(tauri_plugin_log::Builder::default().build())
        .invoke_handler(tauri::generate_handler![get_boot_status])
        .setup(|app| {
            let data_dir = default_data_dir().expect("could not resolve a per-OS app data directory");

            app.manage(LauncherState {
                data_dir: data_dir.clone(),
                app_version: APP_VERSION.to_string(),
                runner: Mutex::new(None),
                last_status: Mutex::new(BootStatus::Progress { message: "starting…".to_string() }),
            });

            // Chosen once, up front, so the injected runtime config (below)
            // and the health-gate poll (in boot::run) agree on the same
            // ports for the lifetime of this run — see BRIEF v1.3 §3. Reuses
            // whatever ports are already baked into an existing config
            // rather than always picking fresh ones (BRIEF v1.8) — see
            // resolve_ports's doc comment for the real bug this fixes.
            let (api_port, tiler_port, db_port) = resolve_ports(&data_dir);

            let runtime_config = FrontendRuntimeConfig::for_ports(api_port, tiler_port, APP_VERSION);

            // Runs before ANY of the page's own JS, on every navigation in
            // this window (splash.html first, then index.html once
            // boot::run() decides the stack is healthy) — see
            // apps/web/src/lib/runtimeConfig.ts, which checks
            // window.__VANTAGE_RUNTIME_CONFIG__ before falling back to
            // fetching /runtime-config.json (the plain docker-compose path).
            let main_window = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("splash.html".into()))
                .title("VANTAGE")
                .inner_size(1440.0, 900.0)
                .min_inner_size(1024.0, 700.0)
                .initialization_script(&runtime_config.to_init_script())
                .visible(true)
                .build()?;
            let _ = main_window;

            build_tray(app.handle())?;

            let app_handle = app.handle().clone();
            std::thread::spawn(move || {
                boot::run(app_handle, data_dir, api_port, tiler_port, db_port);
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running the VANTAGE launcher");
}

/// Tray/menu-bar presence with start/stop/restart/status, logs, data
/// folder, and quit (BRIEF v1.3 §2, §11). Every action here either reads
/// the shared LauncherState's ComposeRunner (populated by boot::run — see
/// state.rs) or is a pure local filesystem/opener call; nothing here makes
/// a network request.
fn build_tray(app: &tauri::AppHandle) -> tauri::Result<()> {
    let restart = MenuItem::with_id(app, "restart", "Restart", true, None::<&str>)?;
    let logs = MenuItem::with_id(app, "logs", "Export Support Bundle…", true, None::<&str>)?;
    let data_folder = MenuItem::with_id(app, "data_folder", "Open Data Folder", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit VANTAGE", true, None::<&str>)?;
    let separator = PredefinedMenuItem::separator(app)?;

    let menu = Menu::with_items(app, &[&restart, &logs, &data_folder, &separator, &quit])?;

    TrayIconBuilder::new()
        .menu(&menu)
        .tooltip("VANTAGE")
        .on_menu_event(|app, event| match event.id().as_ref() {
            "restart" => {
                let app = app.clone();
                std::thread::spawn(move || {
                    let state = app.state::<LauncherState>();
                    let guard = state.runner.lock().expect("runner mutex poisoned");
                    if let Some(runner) = guard.as_ref() {
                        let _ = runner.down();
                        let _ = runner.up();
                    }
                });
            }
            "logs" => {
                let state = app.state::<LauncherState>();
                let guard = state.runner.lock().expect("runner mutex poisoned");
                if let Some(runner) = guard.as_ref() {
                    match support_bundle::export(runner, &state.data_dir, SERVICES, &state.app_version) {
                        Ok(bundle_dir) => {
                            let _ = app.opener().open_path(bundle_dir.display().to_string(), None::<&str>);
                        }
                        Err(e) => log::error!("support bundle export failed: {e}"),
                    }
                }
            }
            "data_folder" => {
                let state = app.state::<LauncherState>();
                let _ = app.opener().open_path(state.data_dir.display().to_string(), None::<&str>);
            }
            "quit" => {
                // Clean shutdown (BRIEF v1.3 §2, §11): release ports via a
                // real `compose down` before exiting, not just process-kill.
                let state = app.state::<LauncherState>();
                if let Some(runner) = state.runner.lock().expect("runner mutex poisoned").as_ref() {
                    let _ = runner.down();
                }
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;
    Ok(())
}
