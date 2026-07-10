//! Thin wrapper around invoking the packaged compose stack (BRIEF v1.3 §2,
//! §4). Deliberately not a compose-file parser/generator — it just builds
//! the right argv and shells out, the same thing an operator would type by
//! hand, so `apps/launcher`'s behavior stays debuggable against a plain
//! terminal.

use std::path::{Path, PathBuf};
use std::process::Output;

use crate::runtime_detect::{external_tool_command, ContainerRuntime};

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

    fn base_args(&self) -> Vec<String> {
        let mut args: Vec<String> = self.runtime.compose_command_prefix().iter().map(|s| s.to_string()).collect();
        args.push("--env-file".into());
        args.push(self.env_file.display().to_string());
        args.push("-f".into());
        args.push(self.compose_file.display().to_string());
        args
    }

    fn run(&self, tail: &[&str]) -> std::io::Result<Output> {
        let args = self.base_args();
        let (program, rest) = args.split_first().expect("base_args always has at least the runtime binary");
        external_tool_command(program).args(rest).args(tail).output()
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
}
