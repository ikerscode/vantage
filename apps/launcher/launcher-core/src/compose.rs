//! Thin wrapper around invoking the packaged compose stack (BRIEF v1.3 §2,
//! §4). Deliberately not a compose-file parser/generator — it just builds
//! the right argv and shells out, the same thing an operator would type by
//! hand, so `apps/launcher`'s behavior stays debuggable against a plain
//! terminal.

use std::io::{Error, ErrorKind, Read};
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::time::{Duration, Instant};

use crate::runtime_detect::{external_tool_command, ContainerRuntime};

// BRIEF v2, found for real, live: `up -d` waits internally on OTHER
// containers' healthchecks (compose's own `depends_on: condition:
// service_healthy`, e.g. api/tiler/worker all waiting on db) -- if a
// dependency can never actually become healthy (confirmed live: db never
// even started because something ENTIRELY UNRELATED already held its
// persisted port), that wait has no natural end. `Command::output()` has
// no timeout of its own, so this hung the whole boot sequence forever,
// with the splash screen frozen and zero feedback -- not a crash, not an
// error, just silence. A bounded timeout turns that into a real, visible
// failure. The child is actually killed on expiry, not just abandoned --
// an abandoned podman-compose process left running in the background is
// exactly the kind of leftover that caused THIS incident's port conflict
// in the first place.
const COMMAND_TIMEOUT: Duration = Duration::from_secs(180);

fn run_with_timeout(cmd: Command) -> std::io::Result<Output> {
    run_with_deadline(cmd, COMMAND_TIMEOUT)
}

fn run_with_deadline(mut cmd: Command, timeout: Duration) -> std::io::Result<Output> {
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());
    let mut child = cmd.spawn()?;
    let deadline = Instant::now() + timeout;

    loop {
        if let Some(status) = child.try_wait()? {
            let mut stdout = Vec::new();
            let mut stderr = Vec::new();
            if let Some(mut o) = child.stdout.take() {
                o.read_to_end(&mut stdout)?;
            }
            if let Some(mut e) = child.stderr.take() {
                e.read_to_end(&mut stderr)?;
            }
            return Ok(Output { status, stdout, stderr });
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Err(Error::new(
                ErrorKind::TimedOut,
                format!(
                    "compose command did not finish within {timeout:?} -- likely waiting on a \
                     dependency (e.g. the database) that never became healthy, possibly because \
                     something else already holds one of this install's configured ports"
                ),
            ));
        }
        std::thread::sleep(Duration::from_millis(200));
    }
}

pub struct ComposeRunner {
    runtime: ContainerRuntime,
    compose_file: PathBuf,
    /// Same file serves as both the compose-level `--env-file` (for ${VAR}
    /// interpolation in the compose YAML) and each service's own
    /// `env_file:` — see docker-compose.prod.yml's header comment for why
    /// this has to be the same file, not two.
    env_file: PathBuf,
}

impl ComposeRunner {
    pub fn new(runtime: ContainerRuntime, compose_file: PathBuf, env_file: PathBuf) -> Self {
        Self { runtime, compose_file, env_file }
    }

    // BRIEF v2, found for real on a live machine: with no explicit project
    // name, Compose derives one from the compose file's own containing
    // directory -- and docker-compose.prod.yml is bundled at
    // <resources>/infra/docker-compose.prod.yml, so its parent directory is
    // literally named "infra", exactly like this repo's OWN dev compose
    // file (infra/docker-compose.yml). Anyone who has ever brought up the
    // dev stack from a checkout of this repo on the same machine ends up
    // with a SECOND, completely unrelated "infra" project using different
    // secrets/env -- and Compose reuses/starts pre-existing containers
    // under a matching project+service name rather than erroring, so the
    // packaged app can silently end up serving through the WRONG stack's
    // containers, with the wrong DEV_TOKEN_SECRET baked in, 401ing every
    // authenticated request with no indication why. An explicit project
    // name removes any dependence on directory layout, in either compose
    // file, forever.
    const PROJECT_NAME: &str = "vantage";

    fn base_args(&self) -> Vec<String> {
        let mut args: Vec<String> = self.runtime.compose_command_prefix().iter().map(|s| s.to_string()).collect();
        args.push("-p".into());
        args.push(Self::PROJECT_NAME.into());
        args.push("--env-file".into());
        args.push(self.env_file.display().to_string());
        args.push("-f".into());
        args.push(self.compose_file.display().to_string());
        args
    }

    fn run(&self, tail: &[&str]) -> std::io::Result<Output> {
        let args = self.base_args();
        let (program, rest) = args.split_first().expect("base_args always has at least the runtime binary");
        let mut cmd = external_tool_command(program);
        cmd.args(rest).args(tail);
        run_with_timeout(cmd)
    }

    /// `compose up -d` — brings up every service in the background. Health
    /// gating (did they actually become healthy) is a separate step, see
    /// health.rs; `up` returning success only means the containers started.
    pub fn up(&self) -> std::io::Result<Output> {
        self.run(&["up", "-d"])
    }

    /// Clean shutdown (BRIEF v1.3 §2, §11) — `down` (not `stop`) so ports
    /// are released, not just paused.
    pub fn down(&self) -> std::io::Result<Output> {
        self.run(&["down"])
    }

    pub fn ps(&self) -> std::io::Result<Output> {
        self.run(&["ps", "--format", "json"])
    }

    pub fn logs(&self, service: Option<&str>) -> std::io::Result<Output> {
        match service {
            Some(s) => self.run(&["logs", "--no-color", s]),
            None => self.run(&["logs", "--no-color"]),
        }
    }

    /// For the support-bundle export (§11) — logs from every service,
    /// concatenated with a header per service so a support engineer doesn't
    /// have to guess which lines came from where.
    pub fn collect_all_logs(&self, services: &[&str]) -> Vec<(String, String)> {
        services
            .iter()
            .map(|svc| {
                let output = self.logs(Some(svc));
                let text = match output {
                    Ok(o) => String::from_utf8_lossy(&o.stdout).to_string(),
                    Err(e) => format!("<failed to collect logs for {svc}: {e}>"),
                };
                (svc.to_string(), text)
            })
            .collect()
    }
}

pub fn compose_file_path(repo_or_resource_root: &Path) -> PathBuf {
    repo_or_resource_root.join("infra").join("docker-compose.prod.yml")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn run_with_deadline_kills_a_hanging_child_instead_of_waiting_forever() {
        // Real reproduction of tonight's incident: `sleep 30` never exits on
        // its own within this test's lifetime, standing in for `up -d`
        // stuck waiting on a healthcheck that can never succeed. Proves two
        // things a mock can't: this returns promptly (not after the full
        // hang), and the process is genuinely killed, not just abandoned to
        // possibly linger in the background afterward (an abandoned
        // podman-compose process is exactly what caused the port conflict
        // this incident started from).
        let mut cmd = Command::new("sleep");
        cmd.arg("30");
        let start = Instant::now();
        let result = run_with_deadline(cmd, Duration::from_millis(300));
        let elapsed = start.elapsed();

        assert!(elapsed < Duration::from_secs(5), "took {elapsed:?} to return -- did not actually time out promptly");
        let err = result.expect_err("a hung child must surface as a real error, not hang the caller forever");
        assert_eq!(err.kind(), std::io::ErrorKind::TimedOut);
    }

    #[test]
    fn run_with_deadline_returns_real_output_for_a_command_that_finishes_in_time() {
        let mut cmd = Command::new("echo");
        cmd.arg("hello");
        let output = run_with_deadline(cmd, Duration::from_secs(5)).expect("echo should succeed well within the timeout");
        assert!(output.status.success());
        assert_eq!(String::from_utf8_lossy(&output.stdout).trim(), "hello");
    }

    #[test]
    fn base_args_put_env_file_before_compose_file_and_use_the_right_runtime_prefix() {
        let runner = ComposeRunner::new(
            ContainerRuntime::Docker,
            PathBuf::from("/opt/vantage/infra/docker-compose.prod.yml"),
            PathBuf::from("/home/user/.local/share/VANTAGE/config/.env"),
        );
        let args = runner.base_args();
        assert_eq!(
            args,
            vec![
                "docker",
                "compose",
                "-p",
                "vantage",
                "--env-file",
                "/home/user/.local/share/VANTAGE/config/.env",
                "-f",
                "/opt/vantage/infra/docker-compose.prod.yml",
            ]
        );
    }

    #[test]
    fn podman_builtin_compose_prefix_is_two_tokens_not_one() {
        let runner = ComposeRunner::new(
            ContainerRuntime::PodmanBuiltinCompose,
            PathBuf::from("compose.yml"),
            PathBuf::from(".env"),
        );
        // Regression guard: "podman compose" is two argv entries (program
        // "podman", first arg "compose"), not a single "podman compose"
        // string — Command::new would try to exec a binary literally named
        // "podman compose" if this collapsed to one token.
        assert_eq!(runner.base_args()[0], "podman");
        assert_eq!(runner.base_args()[1], "compose");
    }

    #[test]
    fn project_name_is_explicit_and_independent_of_the_compose_files_own_directory() {
        // Found for real on a live machine: docker-compose.prod.yml is
        // bundled at <resources>/infra/docker-compose.prod.yml -- same
        // parent directory name ("infra") as this repo's OWN dev compose
        // file. With no explicit project name, Compose derives one from
        // that directory, so the packaged app and a manually-run dev stack
        // resolve to the SAME project ("infra") and can collide: Compose
        // reuses/starts whichever pre-existing "infra_*" containers it
        // finds, which may be the dev stack's own (different secrets, no
        // relation to this install), 401ing every authenticated request
        // with no obvious cause. This must never again depend on directory
        // layout, for either runtime.
        let runner = ComposeRunner::new(
            ContainerRuntime::PodmanStandaloneCompose,
            PathBuf::from("/anything/infra/docker-compose.prod.yml"),
            PathBuf::from("/anything/.env"),
        );
        let args = runner.base_args();
        let p_index = args.iter().position(|a| a == "-p").expect("must always pass an explicit -p project name");
        assert_eq!(args[p_index + 1], "vantage");
    }
}
