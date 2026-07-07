//! Splash-screen health gating (BRIEF v1.3 §2, §11): "poll each service's
//! health endpoint and do not reveal the UI until all are green... honest
//! progress on the splash." No service here is optional-to-wait-for — a
//! half-up stack behind a UI that looks ready is exactly the "fake green
//! check" this whole product line has been built to avoid.

use std::time::Duration;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ServiceHealth {
    Waiting,
    Healthy,
    Unreachable(String),
}

#[derive(Debug, Clone)]
pub struct HealthTarget {
    pub name: &'static str,
    pub url: String,
}

/// api and tiler are the only HTTP-reachable-from-outside services with a
/// /health route the launcher can poll directly; db/redis/minio/inference
/// are proven up transitively (api/tiler won't report healthy until they
/// can reach their own dependencies) — see apps/api/app/routers/health.py
/// and services/tiler's equivalent.
pub fn default_targets(api_port: u16, tiler_port: u16) -> Vec<HealthTarget> {
    vec![
        HealthTarget { name: "api", url: format!("http://localhost:{api_port}/health") },
        HealthTarget { name: "tiler", url: format!("http://localhost:{tiler_port}/health") },
    ]
}

fn check_one(target: &HealthTarget, timeout: Duration) -> ServiceHealth {
    let agent = ureq::AgentBuilder::new().timeout(timeout).build();
    match agent.get(&target.url).call() {
        Ok(resp) if resp.status() == 200 => ServiceHealth::Healthy,
        Ok(resp) => ServiceHealth::Unreachable(format!("HTTP {}", resp.status())),
        Err(e) => ServiceHealth::Unreachable(e.to_string()),
    }
}

/// One poll pass over every target — the caller (Tauri splash screen) is
/// expected to call this in a loop, pushing each result to the UI as
/// "starting database… loading tiler…"-style honest progress, and only
/// stop polling (and reveal the UI) once every target reports Healthy or a
/// max-attempts/timeout budget is exhausted.
pub fn poll_once(targets: &[HealthTarget]) -> Vec<(&'static str, ServiceHealth)> {
    targets.iter().map(|t| (t.name, check_one(t, Duration::from_secs(3)))).collect()
}

pub fn all_healthy(results: &[(&'static str, ServiceHealth)]) -> bool {
    results.iter().all(|(_, h)| *h == ServiceHealth::Healthy)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::TcpListener;
    use std::thread;

    #[test]
    fn default_targets_use_the_ports_passed_in_not_hardcoded_ones() {
        let targets = default_targets(19000, 19001);
        assert_eq!(targets[0].url, "http://localhost:19000/health");
        assert_eq!(targets[1].url, "http://localhost:19001/health");
    }

    #[test]
    fn all_healthy_is_false_if_any_target_is_unreachable() {
        let results = vec![
            ("api", ServiceHealth::Healthy),
            ("tiler", ServiceHealth::Unreachable("connection refused".into())),
        ];
        assert!(!all_healthy(&results));
    }

    #[test]
    fn all_healthy_is_true_only_when_every_target_reports_healthy() {
        let results = vec![("api", ServiceHealth::Healthy), ("tiler", ServiceHealth::Healthy)];
        assert!(all_healthy(&results));
    }

    /// Real end-to-end check against a real TCP listener answering a real
    /// HTTP 200 — not a mock of ureq's internals.
    #[test]
    fn poll_once_reports_healthy_for_a_real_http_200() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        thread::spawn(move || {
            if let Ok((mut stream, _)) = listener.accept() {
                let mut buf = [0u8; 512];
                let _ = stream.read(&mut buf);
                let _ = stream.write_all(b"HTTP/1.1 200 OK\r\ncontent-length: 2\r\n\r\nok");
            }
        });

        let targets = vec![HealthTarget { name: "fake-api", url: format!("http://127.0.0.1:{port}/health") }];
        let results = poll_once(&targets);
        assert_eq!(results[0].1, ServiceHealth::Healthy);
    }

    #[test]
    fn poll_once_reports_unreachable_for_a_port_nothing_is_listening_on() {
        // Port 1 is privileged/unbound in any normal test environment — a
        // real refused connection, not a simulated one.
        let targets = vec![HealthTarget { name: "nothing-here", url: "http://127.0.0.1:1/health".into() }];
        let results = poll_once(&targets);
        assert!(matches!(results[0].1, ServiceHealth::Unreachable(_)));
    }
}
