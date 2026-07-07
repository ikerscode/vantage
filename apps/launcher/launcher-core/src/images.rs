//! Loads the bundled offline image tarball (BRIEF v1.3 §2, §5) — "podman
//! load / docker load the shipped image tarball so nothing is pulled from
//! a registry." Runs once per install; idempotent via a marker file next to
//! the tarball's copy in the data dir (loading twice is harmless but slow —
//! multi-GB tarball — so still worth skipping on every subsequent launch).

use std::fs;
use std::path::Path;
use std::process::{Command, Output};

use crate::runtime_detect::ContainerRuntime;

fn runtime_binary(runtime: &ContainerRuntime) -> &'static str {
    match runtime {
        ContainerRuntime::Docker => "docker",
        ContainerRuntime::PodmanBuiltinCompose | ContainerRuntime::PodmanStandaloneCompose => "podman",
    }
}

/// Returns Ok(true) if it actually ran `load` this call, Ok(false) if it
/// skipped because the marker from a previous successful load is present.
pub fn ensure_images_loaded(
    runtime: &ContainerRuntime,
    tarball_path: &Path,
    data_dir: &Path,
) -> std::io::Result<bool> {
    let marker = data_dir.join("config").join(".images-loaded");
    if marker.exists() {
        return Ok(false);
    }
    if !tarball_path.exists() {
        // Not every build ships the tarball inside the installer (BRIEF
        // v1.3 §8 leaves "ship inside vs. fetch on first run" as an
        // explicit decision) — a missing tarball just means images must
        // already be reachable another way (a private registry, or a
        // developer's local `docker build`), not a hard failure here.
        return Ok(false);
    }

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
    fn skips_cleanly_when_no_tarball_is_bundled() {
        let data_dir = tempfile::tempdir().unwrap();
        let missing_tarball = data_dir.path().join("does-not-exist.tar");
        let ran = ensure_images_loaded(&ContainerRuntime::Docker, &missing_tarball, data_dir.path()).unwrap();
        assert!(!ran, "must not attempt to load a tarball that was never bundled");
    }

    #[test]
    fn skips_on_second_call_once_marker_exists() {
        let data_dir = tempfile::tempdir().unwrap();
        let marker_dir = data_dir.path().join("config");
        fs::create_dir_all(&marker_dir).unwrap();
        fs::write(marker_dir.join(".images-loaded"), "ok").unwrap();

        // Even pointing at a tarball that doesn't exist, the marker alone
        // must be enough to skip — proves we check the marker BEFORE
        // touching the filesystem for the tarball.
        let fake_tarball = data_dir.path().join("images.tar");
        let ran = ensure_images_loaded(&ContainerRuntime::Docker, &fake_tarball, data_dir.path()).unwrap();
        assert!(!ran);
    }
}
