//! First-run secret generation and config templating (BRIEF v1.3 §7, §9).
//!
//! Every install gets its own random DB/MinIO/JWT secrets, written once to
//! `${data_dir}/config/.env` and `${data_dir}/config/db-init/01-roles.sql`.
//! Never regenerated on subsequent runs (that would orphan an
//! already-provisioned Postgres role's password) — if the config file
//! already exists, its DB passwords are read back out instead.

use std::collections::HashMap;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use rand::distributions::Alphanumeric;
use rand::Rng;

const ENV_TEMPLATE: &str = include_str!("../../../../infra/.env.prod.template");
const SQL_TEMPLATE: &str = include_str!("../../../../infra/db-init-prod/01-roles.sql.template");

#[derive(Debug)]
pub enum ConfigError {
    Io(io::Error),
    MissingPlaceholder(String),
}

impl From<io::Error> for ConfigError {
    fn from(e: io::Error) -> Self {
        ConfigError::Io(e)
    }
}

impl std::fmt::Display for ConfigError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ConfigError::Io(e) => write!(f, "io error: {e}"),
            ConfigError::MissingPlaceholder(p) => write!(f, "template still has unrendered placeholder: {p}"),
        }
    }
}

/// Deployment-specific values that aren't secrets but do need to land in the
/// rendered .env (ports, image tags, data dir) — see docker-compose.prod.yml's
/// header comment on why these live in the same file as the secrets.
pub struct DeploymentOptions {
    pub data_dir: PathBuf,
    pub api_port: u16,
    pub tiler_port: u16,
    pub db_port: u16,
    pub api_image: String,
    pub tiler_image: String,
    pub inference_image: String,
    pub inference_device: String,
}

pub struct ConfigPaths {
    pub env_file: PathBuf,
    pub db_init_dir: PathBuf,
    /// True if secrets were freshly generated this call, false if an
    /// existing config was found and reused untouched.
    pub freshly_generated: bool,
}

fn random_token(len: usize) -> String {
    rand::thread_rng()
        .sample_iter(&Alphanumeric)
        .take(len)
        .map(char::from)
        .collect()
}

fn render(template: &str, values: &HashMap<&str, String>) -> Result<String, ConfigError> {
    let mut rendered = template.to_string();
    for (key, value) in values {
        rendered = rendered.replace(&format!("{{{{{key}}}}}"), value);
    }
    if let Some(start) = rendered.find("{{") {
        let end = rendered[start..].find("}}").map(|e| start + e + 2).unwrap_or(start + 2);
        return Err(ConfigError::MissingPlaceholder(rendered[start..end].to_string()));
    }
    Ok(rendered)
}

/// Read back the handful of values a later run needs to stay consistent
/// (DB passwords in particular — regenerating those would leave the
/// already-provisioned Postgres roles unreachable). Simple KEY=VALUE parse;
/// the rendered file is never anything fancier than that.
fn parse_env_file(contents: &str) -> HashMap<String, String> {
    contents
        .lines()
        .filter_map(|line| {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                return None;
            }
            let (key, value) = line.split_once('=')?;
            Some((key.trim().to_string(), value.trim().to_string()))
        })
        .collect()
}

/// Idempotent: if `${data_dir}/config/.env` already exists, leaves it and
/// the rendered SQL untouched and returns freshly_generated=false. Otherwise
/// generates fresh random secrets, renders both templates, writes them, and
/// creates the data directory tree (postgres/minio/redis/logs/config).
pub fn ensure_config(opts: &DeploymentOptions) -> Result<ConfigPaths, ConfigError> {
    let config_dir = opts.data_dir.join("config");
    let db_init_dir = config_dir.join("db-init");
    let env_path = config_dir.join(".env");

    for sub in ["postgres", "minio", "redis", "logs"] {
        fs::create_dir_all(opts.data_dir.join(sub))?;
    }
    fs::create_dir_all(&db_init_dir)?;

    if env_path.exists() {
        return Ok(ConfigPaths {
            env_file: env_path,
            db_init_dir,
            freshly_generated: false,
        });
    }

    let postgres_password = random_token(32);
    let vantage_migrate_password = random_token(32);
    let vantage_app_password = random_token(32);
    let minio_root_password = random_token(32);
    let jwt_secret = random_token(48);
    // SEC-01/SEC-08/SEC-09: same treatment as every other per-install
    // secret above — generated once, never a repo/image default.
    let tiler_token = random_token(48);
    let inference_token = random_token(48);
    let redis_password = random_token(32);
    // BRIEF v1.8: portable alternative to the API's loopback-only network
    // check for /api/auth/dev-token — see FrontendRuntimeConfig's doc
    // comment (config.rs) for why the network heuristic alone isn't
    // enough (found for real on a Podman install).
    let dev_token_secret = random_token(48);

    let mut values: HashMap<&str, String> = HashMap::new();
    values.insert("DATA_DIR", opts.data_dir.display().to_string());
    values.insert("API_PORT", opts.api_port.to_string());
    values.insert("TILER_PORT", opts.tiler_port.to_string());
    values.insert("DB_PORT", opts.db_port.to_string());
    values.insert("API_IMAGE", opts.api_image.clone());
    values.insert("TILER_IMAGE", opts.tiler_image.clone());
    values.insert("INFERENCE_IMAGE", opts.inference_image.clone());
    values.insert("INFERENCE_DEVICE", opts.inference_device.clone());
    values.insert("POSTGRES_PASSWORD", postgres_password);
    values.insert("VANTAGE_MIGRATE_PASSWORD", vantage_migrate_password.clone());
    values.insert("VANTAGE_APP_PASSWORD", vantage_app_password.clone());
    values.insert("MINIO_ROOT_PASSWORD", minio_root_password);
    values.insert("JWT_SECRET", jwt_secret);
    values.insert("TILER_TOKEN", tiler_token);
    values.insert("INFERENCE_TOKEN", inference_token);
    values.insert("REDIS_PASSWORD", redis_password);
    values.insert("DEV_TOKEN_SECRET", dev_token_secret);

    let rendered_env = render(ENV_TEMPLATE, &values)?;
    fs::write(&env_path, rendered_env)?;

    let mut sql_values: HashMap<&str, String> = HashMap::new();
    sql_values.insert("VANTAGE_MIGRATE_PASSWORD", vantage_migrate_password);
    sql_values.insert("VANTAGE_APP_PASSWORD", vantage_app_password);
    let rendered_sql = render(SQL_TEMPLATE, &sql_values)?;
    fs::write(db_init_dir.join("01-roles.sql"), rendered_sql)?;

    Ok(ConfigPaths {
        env_file: env_path,
        db_init_dir,
        freshly_generated: true,
    })
}

/// Convenience for callers (health-gate, logs viewer) that just need to know
/// where things are without re-deriving values already committed to disk.
pub fn read_rendered_value(env_file: &Path, key: &str) -> Option<String> {
    let contents = fs::read_to_string(env_file).ok()?;
    parse_env_file(&contents).get(key).cloned()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn opts(data_dir: PathBuf) -> DeploymentOptions {
        DeploymentOptions {
            data_dir,
            api_port: 8000,
            tiler_port: 8001,
            db_port: 5432,
            api_image: "vantage-api:1.0.0".into(),
            tiler_image: "vantage-tiler:1.0.0".into(),
            inference_image: "vantage-inference:1.0.0".into(),
            inference_device: "cpu".into(),
        }
    }

    #[test]
    fn first_run_generates_fully_rendered_config_with_no_leftover_placeholders() {
        let tmp = tempfile::tempdir().unwrap();
        let paths = ensure_config(&opts(tmp.path().to_path_buf())).unwrap();
        assert!(paths.freshly_generated);

        let env_contents = fs::read_to_string(&paths.env_file).unwrap();
        assert!(!env_contents.contains("{{"), "env file has an unrendered placeholder:\n{env_contents}");
        assert!(env_contents.contains("VANTAGE_DATA_DIR="));
        assert!(env_contents.contains("CORS_ALLOWED_ORIGINS=tauri://localhost,http://tauri.localhost"));

        let sql_contents = fs::read_to_string(paths.db_init_dir.join("01-roles.sql")).unwrap();
        assert!(!sql_contents.contains("{{"), "sql file has an unrendered placeholder:\n{sql_contents}");
        assert!(sql_contents.contains("CREATE ROLE vantage_migrate"));
    }

    #[test]
    fn passwords_in_env_and_sql_agree() {
        let tmp = tempfile::tempdir().unwrap();
        let paths = ensure_config(&opts(tmp.path().to_path_buf())).unwrap();

        let env_contents = fs::read_to_string(&paths.env_file).unwrap();
        let env_values = parse_env_file(&env_contents);
        let migrate_password = env_values.get("VANTAGE_MIGRATE_PASSWORD").unwrap();

        let sql_contents = fs::read_to_string(paths.db_init_dir.join("01-roles.sql")).unwrap();
        assert!(
            sql_contents.contains(&format!("PASSWORD '{migrate_password}'")),
            "vantage_migrate password in the rendered SQL doesn't match the one in .env"
        );
    }

    #[test]
    fn second_run_is_idempotent_and_does_not_rotate_secrets() {
        let tmp = tempfile::tempdir().unwrap();
        let first = ensure_config(&opts(tmp.path().to_path_buf())).unwrap();
        let first_contents = fs::read_to_string(&first.env_file).unwrap();

        let second = ensure_config(&opts(tmp.path().to_path_buf())).unwrap();
        assert!(!second.freshly_generated);
        let second_contents = fs::read_to_string(&second.env_file).unwrap();

        assert_eq!(first_contents, second_contents, "re-running ensure_config must not rotate secrets");
    }

    #[test]
    fn secrets_are_unique_across_installs() {
        let tmp_a = tempfile::tempdir().unwrap();
        let tmp_b = tempfile::tempdir().unwrap();
        let a = ensure_config(&opts(tmp_a.path().to_path_buf())).unwrap();
        let b = ensure_config(&opts(tmp_b.path().to_path_buf())).unwrap();

        let a_secret = read_rendered_value(&a.env_file, "JWT_SECRET").unwrap();
        let b_secret = read_rendered_value(&b.env_file, "JWT_SECRET").unwrap();
        assert_ne!(a_secret, b_secret, "two installs must never share a JWT signing secret");
    }

    #[test]
    fn creates_the_full_data_directory_tree() {
        let tmp = tempfile::tempdir().unwrap();
        ensure_config(&opts(tmp.path().to_path_buf())).unwrap();
        for sub in ["postgres", "minio", "redis", "logs", "config", "config/db-init"] {
            assert!(tmp.path().join(sub).is_dir(), "missing data subdirectory: {sub}");
        }
    }
}
