//! Container runtime detection (BRIEF v1.3 §2: "Do not silently fail" if
//! neither Podman nor Docker is present — surface clear guided instructions
//! instead).

use std::process::Command;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ContainerRuntime {
    /// `podman compose` (built into Podman v4+) — preferred per §4.
    PodmanBuiltinCompose,
    /// Standalone `podman-compose` binary, used when Podman is present but
    /// too old to have the built-in `compose` subcommand.
    PodmanStandaloneCompose,
    Docker,
}

impl ContainerRuntime {
    /// The argv prefix to run compose commands with, e.g. `["podman",
    /// "compose"]` + your own `["-f", ..., "up", "-d"]` tail.
    pub fn compose_command_prefix(&self) -> Vec<&'static str> {
        match self {
            ContainerRuntime::PodmanBuiltinCompose => vec!["podman", "compose"],
            ContainerRuntime::PodmanStandaloneCompose => vec!["podman-compose"],
            ContainerRuntime::Docker => vec!["docker", "compose"],
        }
    }
}

fn command_succeeds(program: &str, args: &[&str]) -> bool {
    Command::new(program)
        .args(args)
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

/// Returns the runtime this machine can actually run compose with, or None
/// if nothing usable was found — the caller (launcher UI) is responsible
/// for turning that into the guided "install Docker or Podman" screen
/// rather than crashing or silently doing nothing.
pub fn detect() -> Option<ContainerRuntime> {
    if command_succeeds("podman", &["--version"]) {
        if command_succeeds("podman", &["compose", "version"]) {
            return Some(ContainerRuntime::PodmanBuiltinCompose);
        }
        if command_succeeds("podman-compose", &["--version"]) {
            return Some(ContainerRuntime::PodmanStandaloneCompose);
        }
    }
    if command_succeeds("docker", &["compose", "version"]) {
        return Some(ContainerRuntime::Docker);
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compose_command_prefix_matches_runtime() {
        assert_eq!(
            ContainerRuntime::PodmanBuiltinCompose.compose_command_prefix(),
            vec!["podman", "compose"]
        );
        assert_eq!(ContainerRuntime::Docker.compose_command_prefix(), vec!["docker", "compose"]);
    }

    #[test]
    fn detect_never_panics_regardless_of_what_is_installed() {
        // This sandbox has neither Docker nor Podman (see PACKAGE_REPORT.md) —
        // the real assertion here is that detect() degrades to None instead
        // of erroring, which is what lets the launcher show a guided
        // install screen instead of crashing on a machine without either.
        let _ = detect();
    }
}
