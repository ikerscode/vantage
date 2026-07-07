//! Local-only support bundle export (BRIEF v1.3 §11): "the launcher can
//! collect all service logs into a local support bundle (zip) the user can
//! hand to support." Explicitly local-only — this writes a file to disk and
//! does nothing else; there is no upload step, no phone-home, matching the
//! §10 "no telemetry... if a support-bundle export exists, it is local-only
//! and user-initiated" requirement.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::compose::ComposeRunner;

/// Writes one text file per service's logs into
/// `${data_dir}/support-bundles/<timestamp>/`, plus a manifest.txt with the
/// app version and which services were included. Returns the bundle
/// directory path. Not actually zipped (no extra dependency for something
/// the user is just going to hand over as a folder or let their file
/// manager zip) — see PACKAGE_REPORT.md if a real .zip is wanted later.
pub fn export(runner: &ComposeRunner, data_dir: &Path, services: &[&str], app_version: &str) -> io::Result<PathBuf> {
    let timestamp = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
    let bundle_dir = data_dir.join("support-bundles").join(timestamp.to_string());
    fs::create_dir_all(&bundle_dir)?;

    let logs = runner.collect_all_logs(services);
    for (service, text) in &logs {
        fs::write(bundle_dir.join(format!("{service}.log")), text)?;
    }

    let manifest = format!(
        "VANTAGE support bundle\nversion: {app_version}\ngenerated_at_unix: {timestamp}\nservices: {}\n",
        services.join(", ")
    );
    fs::write(bundle_dir.join("manifest.txt"), manifest)?;

    Ok(bundle_dir)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::runtime_detect::ContainerRuntime;

    #[test]
    fn writes_one_log_file_per_service_plus_a_manifest() {
        let data_dir = tempfile::tempdir().unwrap();
        // A runtime binary that doesn't exist is fine for this test —
        // ComposeRunner::logs() surfaces the failure as text content rather
        // than erroring, so export() still produces a bundle (with an
        // honest "<failed to collect logs...>" line) instead of crashing
        // when a service's logs can't be fetched.
        let runner = ComposeRunner::new(
            ContainerRuntime::Docker,
            PathBuf::from("/nonexistent/compose.yml"),
            PathBuf::from("/nonexistent/.env"),
        );

        let bundle_dir = export(&runner, data_dir.path(), &["api", "tiler"], "0.1.0").unwrap();

        assert!(bundle_dir.join("api.log").is_file());
        assert!(bundle_dir.join("tiler.log").is_file());
        assert!(bundle_dir.join("manifest.txt").is_file());
        let manifest = fs::read_to_string(bundle_dir.join("manifest.txt")).unwrap();
        assert!(manifest.contains("version: 0.1.0"));
        assert!(manifest.contains("api, tiler"));
    }

    #[test]
    fn bundle_lands_under_the_data_dirs_support_bundles_subdirectory() {
        let data_dir = tempfile::tempdir().unwrap();
        let runner = ComposeRunner::new(
            ContainerRuntime::Docker,
            PathBuf::from("/nonexistent/compose.yml"),
            PathBuf::from("/nonexistent/.env"),
        );
        let bundle_dir = export(&runner, data_dir.path(), &["api"], "0.1.0").unwrap();
        assert!(bundle_dir.starts_with(data_dir.path().join("support-bundles")));
    }
}
