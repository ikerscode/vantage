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

/// Builds a `Command` for an external system tool (podman/podman-compose/
/// docker) with the AppImage runtime's own self-containment env vars
/// stripped. Found for real (BRIEF v2, live-tested against the packaged
/// .AppImage): AppRun sets `PYTHONHOME`/`PYTHONPATH` so VANTAGE's *own*
/// bundled GTK/WebKit libraries resolve correctly, but those same vars leak
/// into every subprocess this binary spawns — and `podman-compose` (the
/// fallback for Podman installs too old to have the built-in `compose`
/// subcommand) is itself a Python script. Inheriting the bundle's
/// `PYTHONHOME` pointed the system `python3` at the wrong standard library
/// entirely (`Fatal Python error: Failed to import encodings module`),
/// making `podman-compose` fail every single invocation — not a flaky
/// failure, 100% reproducible — so `detect()` always concluded "no runtime
/// found" even with a perfectly good Podman install present. `LD_LIBRARY_PATH`
/// is stripped too on the same principle: it's just as capable of pointing
/// any dynamically-linked external binary (podman/docker themselves
/// included) at the bundle's own libc/libssl instead of the system's.
pub fn external_tool_command(program: &str) -> Command {
    let mut cmd = Command::new(program);
    cmd.env_remove("LD_LIBRARY_PATH");
    cmd.env_remove("PYTHONHOME");
    cmd.env_remove("PYTHONPATH");
    cmd
}

fn command_succeeds(program: &str, args: &[&str]) -> bool {
    external_tool_command(program)
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
    fn external_tool_command_strips_appimage_env_vars_from_the_child_process() {
        // Real reproduction (BRIEF v2, against the actual published
        // .AppImage): inheriting PYTHONHOME from AppRun broke podman-compose
        // (a Python script) with a genuine, 100%-reproducible "Fatal Python
        // error: Failed to import encodings module" -- proves the fix
        // end to end (a real child process's real environment), not just
        // that env_remove was called on the builder.
        std::env::set_var("PYTHONHOME", "/should/not/reach/child");
        std::env::set_var("PYTHONPATH", "/should/not/reach/child");
        std::env::set_var("LD_LIBRARY_PATH", "/should/not/reach/child");

        let output = external_tool_command("env").output().expect("`env` must exist on the ubuntu-latest test runner");
        let stdout = String::from_utf8_lossy(&output.stdout).to_string();

        std::env::remove_var("PYTHONHOME");
        std::env::remove_var("PYTHONPATH");
        std::env::remove_var("LD_LIBRARY_PATH");

        assert!(!stdout.contains("PYTHONHOME"), "PYTHONHOME leaked into the child process:\n{stdout}");
        assert!(!stdout.contains("PYTHONPATH"), "PYTHONPATH leaked into the child process:\n{stdout}");
        assert!(!stdout.contains("LD_LIBRARY_PATH"), "LD_LIBRARY_PATH leaked into the child process:\n{stdout}");
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
