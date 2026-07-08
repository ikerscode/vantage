//! Loads the offline image tarball (BRIEF v1.3 §2, §5; path decision
//! reconciled in BRIEF v1.6 — see OFFLINE_BUNDLE_REPORT.md) — "podman load
//! / docker load the shipped image tarball so nothing is pulled from a
//! registry." Runs once per install; idempotent via a marker file next to
//! the tarball's copy in the data dir (loading twice is harmless but slow —
//! multi-GB tarball — so still worth skipping on every subsequent launch).
//!
//! The tarball (~6.6 GiB measured for real — OFFLINE_BUNDLE_REPORT.md)
//! does NOT ship inside the installer: it's over 3x GitHub's hard 2 GiB
//! release-asset cap, and embedding it would balloon every installer to
//! match. It ships as chunked release assets the operator downloads once
//! and reassembles (see docs/AIRGAP.md), then places in VANTAGE's data
//! directory. `ensure_images_loaded` checks a list of candidate paths, not
//! one fixed location, so it finds the tarball wherever it actually ends
//! up — a bundled resource path (kept as a candidate in case a future
//! build does embed it) and the operator-provided data-dir path both work,
//! in the order given.

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

use crate::runtime_detect::ContainerRuntime;

fn runtime_binary(runtime: &ContainerRuntime) -> &'static str {
    match runtime {
        ContainerRuntime::Docker => "docker",
        ContainerRuntime::PodmanBuiltinCompose | ContainerRuntime::PodmanStandaloneCompose => "podman",
    }
}

/// The first candidate path that actually exists on disk, in the order
/// given — a small, pure helper split out so path-selection is testable
/// without needing a real container runtime installed.
fn select_tarball<'a>(tarball_candidates: &'a [PathBuf]) -> Option<&'a PathBuf> {
    tarball_candidates.iter().find(|p| p.exists())
}

/// Returns Ok(true) if it actually ran `load` this call, Ok(false) if it
/// skipped because the marker from a previous successful load is present.
pub fn ensure_images_loaded(
    runtime: &ContainerRuntime,
    tarball_candidates: &[PathBuf],
    data_dir: &Path,
) -> std::io::Result<bool> {
    let marker = data_dir.join("config").join(".images-loaded");
    if marker.exists() {
        return Ok(false);
    }
    let Some(tarball_path) = select_tarball(tarball_candidates) else {
        // Neither the bundled-resource path nor the operator-provided
        // data-dir path has a tarball yet — this just means images must
        // already be reachable another way (a private registry, or a
        // developer's local `docker build`), not a hard failure here.
        return Ok(false);
    };

    let output = run_load(runtime, tarball_path)?;
    if output.status.success() {
        if let Some(parent) = marker.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(&marker, "ok")?;
    }
    Ok(output.status.success())
}

fn run_load(runtime: &ContainerRuntime, tarball_path: &Path) -> std::io::Result<Output> {
    Command::new(runtime_binary(runtime)).arg("load").arg("-i").arg(tarball_path).output()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn skips_cleanly_when_no_tarball_is_found_at_any_candidate() {
        let data_dir = tempfile::tempdir().unwrap();
        let candidates = vec![
            data_dir.path().join("bundled").join("does-not-exist.tar"),
            data_dir.path().join("does-not-exist-either.tar"),
        ];
        let ran = ensure_images_loaded(&ContainerRuntime::Docker, &candidates, data_dir.path()).unwrap();
        assert!(!ran, "must not attempt to load a tarball that isn't at any candidate path");
    }

    #[test]
    fn skips_on_second_call_once_marker_exists() {
        let data_dir = tempfile::tempdir().unwrap();
        let marker_dir = data_dir.path().join("config");
        fs::create_dir_all(&marker_dir).unwrap();
        fs::write(marker_dir.join(".images-loaded"), "ok").unwrap();

        // Even pointing at candidates that don't exist, the marker alone
        // must be enough to skip — proves we check the marker BEFORE
        // touching the filesystem for any candidate tarball.
        let candidates = vec![data_dir.path().join("images.tar")];
        let ran = ensure_images_loaded(&ContainerRuntime::Docker, &candidates, data_dir.path()).unwrap();
        assert!(!ran);
    }

    // BRIEF v1.6: the tarball ships as a separate operator download (see
    // OFFLINE_BUNDLE_REPORT.md), placed in the data dir, not the bundled
    // resource dir — this is the primary real-world path now, so
    // path-selection gets direct coverage. Split out as `select_tarball`
    // (pure, no subprocess) rather than asserting through
    // `ensure_images_loaded`, which would need a real container runtime
    // installed on whatever machine runs `cargo test` just to observe
    // which path it picked.
    #[test]
    fn select_tarball_finds_a_later_candidate_when_earlier_ones_are_absent() {
        let data_dir = tempfile::tempdir().unwrap();
        let bundled_path = data_dir.path().join("bundled-does-not-exist.tar");
        let operator_provided_path = data_dir.path().join("vantage-images-1.0.0.tar");
        fs::write(&operator_provided_path, b"not a real tarball, just needs to exist").unwrap();

        let candidates = vec![bundled_path, operator_provided_path.clone()];
        assert_eq!(select_tarball(&candidates), Some(&operator_provided_path));
    }

    #[test]
    fn select_tarball_prefers_the_first_existing_candidate() {
        let data_dir = tempfile::tempdir().unwrap();
        let first = data_dir.path().join("first.tar");
        let second = data_dir.path().join("second.tar");
        fs::write(&first, b"placeholder").unwrap();
        fs::write(&second, b"placeholder").unwrap();

        let candidates = vec![first.clone(), second];
        assert_eq!(select_tarball(&candidates), Some(&first));
    }

    #[test]
    fn select_tarball_returns_none_when_nothing_exists() {
        let data_dir = tempfile::tempdir().unwrap();
        let candidates = vec![data_dir.path().join("a.tar"), data_dir.path().join("b.tar")];
        assert_eq!(select_tarball(&candidates), None);
    }
}
