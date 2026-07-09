//! Where this app's persistent state lives (BRIEF v1.3 §7: "Data directory
//! selection"). The wizard lets an operator override this; these are just
//! the per-OS defaults it pre-fills.

use std::net::TcpListener;
use std::path::PathBuf;

/// `dirs::data_dir()` already resolves to the right per-OS convention:
/// `~/.local/share` (XDG) on Linux, `~/Library/Application Support` on
/// macOS, `%APPDATA%` on Windows.
pub fn default_data_dir() -> Option<PathBuf> {
    dirs::data_dir().map(|d| d.join("VANTAGE"))
}

/// BRIEF v1.3 §3: ports must be chosen at launch, not hardcoded, "so the
/// port can be chosen/avoid conflicts". Tries the preferred port first
/// (keeps behavior predictable/debuggable on a clean machine); only hunts
/// for a free one if that's already taken by something else.
pub fn find_available_port(preferred: u16) -> u16 {
    if TcpListener::bind(("127.0.0.1", preferred)).is_ok() {
        return preferred;
    }
    TcpListener::bind(("127.0.0.1", 0))
        .and_then(|l| l.local_addr())
        .map(|addr| addr.port())
        .unwrap_or(preferred)
}

/// Frontend runtime config (see apps/web/src/lib/runtimeConfig.ts). Rather
/// than writing runtime-config.json into the bundled webview assets at
/// runtime (fragile: may be read-only, breaks macOS code-signing, wrong
/// path across bundle formats), the launcher injects this as
/// `window.__VANTAGE_RUNTIME_CONFIG__` via a Tauri `initialization_script`
/// that runs before the page's own JS — see src-tauri/src/main.rs.
/// runtimeConfig.ts checks that global first and only falls back to
/// fetching /runtime-config.json for plain (non-Tauri) deployments.
#[derive(serde::Serialize)]
pub struct FrontendRuntimeConfig {
    #[serde(rename = "apiBaseUrl")]
    pub api_base_url: String,
    #[serde(rename = "tilerBaseUrl")]
    pub tiler_base_url: String,
    /// Surfaced in-app (BRIEF v1.3 §11: "version stamp visible in-app") —
    /// see StatusStrip.tsx.
    #[serde(rename = "appVersion")]
    pub app_version: String,
    /// BRIEF v1.8, found for real on a Podman user's machine: the API's
    /// dev-token endpoint gates on "is this caller loopback", determined
    /// via a container-runtime-specific network heuristic that doesn't
    /// generalize to every runtime (confirmed: works under Docker, not
    /// under Podman's rootless networking). This per-install secret is
    /// the portable alternative — same pattern as tiler_token/
    /// inference_token (apps/api/app/core/config.py) — presented as a
    /// header on the dev-token call (apps/web/src/api/auth.ts) as an
    /// ADDITIONAL accepted path, not a replacement for the loopback
    /// check. Empty string for non-Tauri deployments (plain
    /// docker-compose), where the existing loopback check already works.
    #[serde(rename = "devTokenSecret")]
    pub dev_token_secret: String,
}

impl FrontendRuntimeConfig {
    pub fn for_ports(
        api_port: u16,
        tiler_port: u16,
        app_version: impl Into<String>,
        dev_token_secret: impl Into<String>,
    ) -> Self {
        Self {
            api_base_url: format!("http://localhost:{api_port}"),
            tiler_base_url: format!("http://localhost:{tiler_port}"),
            app_version: app_version.into(),
            dev_token_secret: dev_token_secret.into(),
        }
    }

    pub fn to_json_string(&self) -> String {
        serde_json::to_string_pretty(self).expect("FrontendRuntimeConfig is always serializable")
    }

    /// The exact JS statement to hand to `initialization_script`.
    pub fn to_init_script(&self) -> String {
        format!("window.__VANTAGE_RUNTIME_CONFIG__ = {};", self.to_json_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_data_dir_ends_in_vantage() {
        let dir = default_data_dir().expect("dirs::data_dir() should resolve on a real OS");
        assert_eq!(dir.file_name().unwrap(), "VANTAGE");
    }

    #[test]
    fn frontend_runtime_config_matches_apps_web_schema() {
        let cfg = FrontendRuntimeConfig::for_ports(18000, 18001, "0.1.0", "sekret");
        let json = cfg.to_json_string();
        assert!(json.contains("\"apiBaseUrl\": \"http://localhost:18000\""));
        assert!(json.contains("\"tilerBaseUrl\": \"http://localhost:18001\""));
        assert!(json.contains("\"appVersion\": \"0.1.0\""));
        assert!(json.contains("\"devTokenSecret\": \"sekret\""));
    }

    #[test]
    fn init_script_is_a_single_valid_assignment_statement() {
        let cfg = FrontendRuntimeConfig::for_ports(8000, 8001, "0.1.0", "sekret");
        let script = cfg.to_init_script();
        assert!(script.starts_with("window.__VANTAGE_RUNTIME_CONFIG__ = {"));
        assert!(script.trim_end().ends_with("};"));
    }

    #[test]
    fn find_available_port_returns_the_preferred_port_when_it_is_free() {
        // Bind-and-drop to get a port that's genuinely free right now,
        // rather than guessing an arbitrary high number that might collide
        // with something else running on this machine.
        let probe = TcpListener::bind("127.0.0.1:0").unwrap();
        let free_port = probe.local_addr().unwrap().port();
        drop(probe);

        assert_eq!(find_available_port(free_port), free_port);
    }

    #[test]
    fn find_available_port_falls_back_when_preferred_port_is_taken() {
        let held = TcpListener::bind("127.0.0.1:0").unwrap();
        let taken_port = held.local_addr().unwrap().port();

        let chosen = find_available_port(taken_port);
        assert_ne!(chosen, taken_port, "must not return a port something else is already bound to");
    }
}
