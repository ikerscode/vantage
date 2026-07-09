use std::path::PathBuf;
use std::sync::Mutex;

use vantage_launcher_core::compose::ComposeRunner;

/// BRIEF v1.8, found for real on a user's machine: boot::run's progress/
/// failure events fire on a background thread started immediately in
/// main.rs's setup() hook, which can race the splash webview's own async
/// page load — if boot fails fast (confirmed: a `compose up` error can
/// surface within ~4 seconds), the "vantage://boot-failed" event can be
/// emitted before splash.html has finished loading and attached its
/// listener, and Tauri does not buffer/replay events for late listeners.
/// The event is silently lost and the splash screen is stuck on its
/// static default text forever, with no visible indication anything
/// failed — even though the Rust side handled it correctly. Recording
/// the latest status here lets the frontend pull the CURRENT state via a
/// command (get_boot_status, main.rs) the moment it loads, closing the
/// race regardless of how fast boot::run finishes.
#[derive(Clone, serde::Serialize)]
#[serde(tag = "kind")]
pub enum BootStatus {
    Progress { message: String },
    Failed { message: String },
}

/// Shared across the tray's menu callbacks and boot::run — boot::run fills
/// in `runner` once it has actually resolved a container runtime and
/// started the stack; until then tray actions that need it (restart, logs,
/// quit's `compose down`) degrade to a clear "still starting up" message
/// instead of panicking on a None.
pub struct LauncherState {
    pub data_dir: PathBuf,
    pub app_version: String,
    pub runner: Mutex<Option<ComposeRunner>>,
    pub last_status: Mutex<BootStatus>,
}

pub const SERVICES: &[&str] = &["db", "redis", "minio", "api", "worker", "beat", "tiler", "inference"];
