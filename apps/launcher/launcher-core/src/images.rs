//! Gets the production container images onto the machine, however they
//! need to get there (BRIEF v1.3 §2, §5; BRIEF v1.6 chunked-bundle path;
//! BRIEF v1.7 thin/online path). Runs once per install; idempotent via a
//! marker file next to the tarball's copy in the data dir.
//!
//! Two real paths, for two real audiences, both proven end to end (see
//! PACKAGING_V2_REPORT.md):
//!
//! 1. **Air-gap bundle** (BRIEF v1.6): the operator downloads the chunked
//!    offline tarball (~2.7 GiB as of BRIEF v1.7's size fixes — was 6.6
//!    GiB before those) separately and places it in VANTAGE's data
//!    directory before first launch. `select_tarball` checks a list of
//!    candidate paths, not one fixed location — the bundled-resource path
//!    (kept in case a future build ever does embed it) and the
//!    operator-provided data-dir path both work, in the order given.
//! 2. **Thin/online installer** (BRIEF v1.7): most users don't need the
//!    air-gap bundle at all. If no local tarball is found, and this
//!    machine has network access, `docker`/`podman pull` the same
//!    production images from GHCR (pushed by release.yml, tagged by
//!    VANTAGE_VERSION) instead of silently doing nothing — the previous
//!    behavior here would leave `docker compose up` to fail later with a
//!    cryptic "pull access denied" error, since these images were never on
//!    any registry before BRIEF v1.7.
//!
//! If NEITHER a bundled tarball nor network access is available, that's a
//! genuinely unrecoverable state — this returns a real Err with an
//! actionable message, not a silent Ok(false) that leaves the caller to
//! discover the problem downstream.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::Output;

use crate::runtime_detect::{external_tool_command, ContainerRuntime};

/// (local tag docker-compose.prod.yml's defaults expect, GHCR image
/// pulled and re-tagged to match it) — re-tagging after pull means nothing
/// downstream needs to know or care which source the images actually came
/// from.
pub const REQUIRED_IMAGES: &[(&str, &str)] = &[
    ("vantage-api:1.0.0", "ghcr.io/ikerscode/vantage-api:1.0.0"),
    ("vantage-tiler:1.0.0", "ghcr.io/ikerscode/vantage-tiler:1.0.0"),
    ("vantage-inference:1.0.0", "ghcr.io/ikerscode/vantage-inference:1.0.0"),
    ("vantage-pgstac-migrate:1.0.0", "ghcr.io/ikerscode/vantage-pgstac-migrate:1.0.0"),
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ImageSource {
    /// The marker from a previous successful run of THIS app version was
    /// already present.
    AlreadyLoaded,
    /// Loaded from a local (bundled or operator-provided) tarball.
    Tarball,
    /// Pulled from the container registry (thin/online installer path).
    Registry,
}

/// BRIEF v2, found for real on a live install: the marker used to be a
/// bare "ok" written once, ever — so an app upgrade NEVER refreshed the
/// container images. Image references are deliberately pinned to a stable
/// tag (1.0.0 — see release.yml's publish-images comments for why), and
/// each release re-pushes that tag with current code, so an installed
/// machine could carry a months-stale backend forever while the launcher
/// updated around it (confirmed live: an API missing input validation
/// shipped 3 releases earlier accepted a 32.5M-km² AOI whose imagery
/// search then hung the whole UI). The marker now records WHICH app
/// version loaded images; any mismatch (including the legacy "ok"
/// content) re-loads/re-pulls, which is cheap when nothing changed
/// (layer-cached) and correct when something did.
fn marker_is_current(marker: &Path, app_version: &str) -> bool {
    fs::read_to_string(marker).map(|content| content.trim() == app_version).unwrap_or(false)
}

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

pub fn ensure_images_loaded(
    runtime: &ContainerRuntime,
    tarball_candidates: &[PathBuf],
    data_dir: &Path,
    app_version: &str,
) -> io::Result<ImageSource> {
    let marker = data_dir.join("config").join(".images-loaded");
    if marker_is_current(&marker, app_version) {
        return Ok(ImageSource::AlreadyLoaded);
    }

    if let Some(tarball_path) = select_tarball(tarball_candidates) {
        let output = run_load(runtime, tarball_path)?;
        if !output.status.success() {
            return Err(io::Error::other(format!(
                "{} load failed against the offline bundle at {}: {}",
                runtime_binary(runtime),
                tarball_path.display(),
                String::from_utf8_lossy(&output.stderr)
            )));
        }
        write_marker(&marker, app_version)?;
        return Ok(ImageSource::Tarball);
    }

    // No bundled tarball anywhere — thin/online installer path.
    for (local_tag, ghcr_ref) in REQUIRED_IMAGES {
        let pull = run_pull(runtime, ghcr_ref)?;
        if !pull.status.success() {
            return Err(io::Error::other(actionable_no_images_error(ghcr_ref, &pull)));
        }
        let tag = run_tag(runtime, ghcr_ref, local_tag)?;
        if !tag.status.success() {
            return Err(io::Error::other(format!(
                "pulled {ghcr_ref} but couldn't tag it as {local_tag}: {}",
                String::from_utf8_lossy(&tag.stderr)
            )));
        }
    }
    write_marker(&marker, app_version)?;
    Ok(ImageSource::Registry)
}

fn actionable_no_images_error(ghcr_ref: &str, pull: &Output) -> String {
    format!(
        "no offline image bundle was found, and pulling {ghcr_ref} from the container \
         registry failed:\n{}\n\n\
         Either place the offline bundle in your data directory before launching \
         (see docs/AIRGAP.md), or connect this machine to the internet so images can \
         be pulled automatically.",
        String::from_utf8_lossy(&pull.stderr)
    )
}

fn write_marker(marker: &Path, app_version: &str) -> io::Result<()> {
    if let Some(parent) = marker.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(marker, app_version)
}

fn run_load(runtime: &ContainerRuntime, tarball_path: &Path) -> io::Result<Output> {
    external_tool_command(runtime_binary(runtime)).arg("load").arg("-i").arg(tarball_path).output()
}

fn run_pull(runtime: &ContainerRuntime, image: &str) -> io::Result<Output> {
    external_tool_command(runtime_binary(runtime)).arg("pull").arg(image).output()
}

fn run_tag(runtime: &ContainerRuntime, src: &str, dst: &str) -> io::Result<Output> {
    external_tool_command(runtime_binary(runtime)).arg("tag").arg(src).arg(dst).output()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn already_loaded_short_circuits_before_touching_any_candidate() {
        let data_dir = tempfile::tempdir().unwrap();
        let marker_dir = data_dir.path().join("config");
        fs::create_dir_all(&marker_dir).unwrap();
        fs::write(marker_dir.join(".images-loaded"), "0.1.20").unwrap();

        // Even pointing at candidates that don't exist, a marker matching
        // this app version must be enough to skip — proves we check the
        // marker BEFORE touching the filesystem for any candidate tarball
        // (and, by the same logic, before ever attempting a registry pull).
        let candidates = vec![data_dir.path().join("images.tar")];
        let result =
            ensure_images_loaded(&ContainerRuntime::Docker, &candidates, data_dir.path(), "0.1.20").unwrap();
        assert_eq!(result, ImageSource::AlreadyLoaded);
    }

    #[test]
    fn marker_from_an_older_app_version_does_not_short_circuit() {
        // The real upgrade bug (BRIEF v2, found live): the marker used to
        // be version-blind, so images loaded once were NEVER refreshed —
        // an install could run a months-stale backend forever. A marker
        // from any other version (including the legacy "ok" content, which
        // every pre-fix install has on disk) must NOT count as current.
        let dir = tempfile::tempdir().unwrap();
        let marker = dir.path().join(".images-loaded");

        fs::write(&marker, "0.1.19").unwrap();
        assert!(!marker_is_current(&marker, "0.1.20"), "an older version's marker must not be treated as current");

        fs::write(&marker, "ok").unwrap();
        assert!(!marker_is_current(&marker, "0.1.20"), "the legacy 'ok' marker must not be treated as current");

        assert!(!marker_is_current(&dir.path().join("missing"), "0.1.20"), "a missing marker is never current");

        fs::write(&marker, "0.1.20\n").unwrap();
        assert!(marker_is_current(&marker, "0.1.20"), "same version (even with trailing whitespace) is current");
    }

    // BRIEF v1.6/v1.7: the tarball ships as a separate operator download
    // (see OFFLINE_BUNDLE_REPORT.md), placed in the data dir, not the
    // bundled resource dir — this is the primary air-gap-path real-world
    // location, so path-selection gets direct coverage. Split out as
    // `select_tarball` (pure, no subprocess) rather than asserting through
    // `ensure_images_loaded`, which would need a real container runtime
    // installed on whatever machine runs `cargo test` just to observe
    // which path it picked — the actual load/pull subprocess behavior is
    // proven by the real acceptance tests instead (see
    // PACKAGING_V2_REPORT.md / OFFLINE_BUNDLE_REPORT.md), not a mock here.
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

    #[test]
    fn required_images_local_tags_match_docker_compose_prod_defaults() {
        // Not exhaustive proof the compose file agrees (that needs the
        // real acceptance test), but a real regression guard: if someone
        // renames a local tag here without updating the other, this catches
        // the obvious case of the four expected services going missing.
        let local_tags: Vec<&str> = REQUIRED_IMAGES.iter().map(|(local, _)| *local).collect();
        assert_eq!(
            local_tags,
            vec![
                "vantage-api:1.0.0",
                "vantage-tiler:1.0.0",
                "vantage-inference:1.0.0",
                "vantage-pgstac-migrate:1.0.0",
            ]
        );
    }

    #[test]
    fn actionable_error_names_the_failed_image_and_points_at_both_real_fixes() {
        let fake_output = Output {
            status: std::process::ExitStatus::default(),
            stdout: Vec::new(),
            stderr: b"Error response from daemon: Get \"https://ghcr.io/v2/\": no such host".to_vec(),
        };
        let msg = actionable_no_images_error("ghcr.io/ikerscode/vantage-api:1.0.0", &fake_output);
        assert!(msg.contains("ghcr.io/ikerscode/vantage-api:1.0.0"));
        assert!(msg.contains("docs/AIRGAP.md"));
        assert!(msg.contains("connect this machine to the internet"));
        assert!(msg.contains("no such host"));
    }
}
