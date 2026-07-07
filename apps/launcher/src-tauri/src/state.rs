use std::path::PathBuf;
use std::sync::Mutex;

use vantage_launcher_core::compose::ComposeRunner;

/// Shared across the tray's menu callbacks and boot::run — boot::run fills
/// in `runner` once it has actually resolved a container runtime and
/// started the stack; until then tray actions that need it (restart, logs,
/// quit's `compose down`) degrade to a clear "still starting up" message
/// instead of panicking on a None.
pub struct LauncherState {
    pub data_dir: PathBuf,
    pub app_version: String,
    pub runner: Mutex<Option<ComposeRunner>>,
}

pub const SERVICES: &[&str] = &["db", "redis", "minio", "api", "worker", "beat", "tiler", "inference"];
