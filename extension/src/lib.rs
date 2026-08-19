use std::env;

use schemars::JsonSchema;
use serde::Deserialize;
use zed::settings::ContextServerSettings;
use zed_extension_api::{
    self as zed, Command, ContextServerConfiguration, ContextServerId, DownloadedFileType, Project,
    Result, serde_json,
};

const SERVER_REVISION: &str = "a3a0d40";
const SERVER_PATH: &str = "auto_commit_mcp.py";

fn default_enabled() -> bool {
    true
}

fn default_interval_seconds() -> u64 {
    5
}

fn default_commit_message() -> String {
    "chore: auto-commit".to_string()
}

fn default_include_untracked() -> bool {
    true
}

#[derive(Debug, Deserialize, JsonSchema)]
struct AutoCommitSettings {
    #[serde(default = "default_enabled")]
    enabled: bool,
    #[serde(default = "default_interval_seconds")]
    #[schemars(range(min = 1, max = 86400))]
    interval_seconds: u64,
    #[serde(default = "default_commit_message")]
    commit_message: String,
    #[serde(default = "default_include_untracked")]
    include_untracked: bool,
}

impl Default for AutoCommitSettings {
    fn default() -> Self {
        Self {
            enabled: default_enabled(),
            interval_seconds: default_interval_seconds(),
            commit_message: default_commit_message(),
            include_untracked: default_include_untracked(),
        }
    }
}

struct AutoCommitExtension;

impl zed::Extension for AutoCommitExtension {
    fn new() -> Self {
        Self
    }

    fn context_server_command(
        &mut self,
        _context_server_id: &ContextServerId,
        project: &Project,
    ) -> Result<Command> {
        let settings = ContextServerSettings::for_project("auto-commit", project)?;
        let settings: AutoCommitSettings = settings
            .settings
            .map(serde_json::from_value)
            .transpose()
            .map_err(|error| format!("invalid Auto Commit settings: {error}"))?
            .unwrap_or_default();

        if settings.commit_message.trim().is_empty() {
            return Err("Auto Commit's commit_message must not be empty".to_string());
        }

        let server_path = env::current_dir()
            .map_err(|error| error.to_string())?
            .join(SERVER_PATH);
        if !server_path.is_file() {
            let download_url = format!(
                "https://raw.githubusercontent.com/Zamiell/zed-auto-commit/{SERVER_REVISION}/server/{SERVER_PATH}"
            );
            zed::download_file(&download_url, SERVER_PATH, DownloadedFileType::Uncompressed)?;
        }

        Ok(Command {
            command: "python3".to_string(),
            args: vec![server_path.to_string_lossy().to_string()],
            env: vec![
                (
                    "ZED_AUTO_COMMIT_ENABLED".to_string(),
                    settings.enabled.to_string(),
                ),
                (
                    "ZED_AUTO_COMMIT_INTERVAL_SECONDS".to_string(),
                    settings.interval_seconds.to_string(),
                ),
                (
                    "ZED_AUTO_COMMIT_MESSAGE".to_string(),
                    settings.commit_message,
                ),
                (
                    "ZED_AUTO_COMMIT_INCLUDE_UNTRACKED".to_string(),
                    settings.include_untracked.to_string(),
                ),
            ],
        })
    }

    fn context_server_configuration(
        &mut self,
        _context_server_id: &ContextServerId,
        _project: &Project,
    ) -> Result<Option<ContextServerConfiguration>> {
        let settings_schema = serde_json::to_string(&schemars::schema_for!(AutoCommitSettings))
            .map_err(|error| error.to_string())?;

        Ok(Some(ContextServerConfiguration {
            installation_instructions: include_str!("../configuration/installation.md").to_string(),
            default_settings: include_str!("../configuration/default_settings.jsonc").to_string(),
            settings_schema,
        }))
    }
}

zed::register_extension!(AutoCommitExtension);
