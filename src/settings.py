"""Application settings via pydantic-settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AnthropicSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORK_AGENTS_ANTHROPIC_")

    api_key: str = ""
    default_model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 4096


class JiraSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORK_AGENTS_JIRA_")

    server_url: str = ""
    email: str = ""
    api_token: str = ""
    project_key: str = "PROJ"
    poll_interval_seconds: int = 60
    # Set to False on corporate networks doing TLS interception
    # (e.g. Palo Alto, ZScaler) where Python's requests can't validate the
    # corporate-signed cert. Use ca_bundle instead when possible.
    verify_ssl: bool = True
    ca_bundle: str = ""


class GitHubSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORK_AGENTS_GITHUB_")

    token: str = ""
    repo: str = ""
    base_branch: str = "main"


class PipelineSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORK_AGENTS_PIPELINE_")

    max_feedback_loops: int = 3
    approval_timeout_hours: int = 24
    max_concurrent_tickets: int = 10


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORK_AGENTS_SERVER_")

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = Field(default=["http://localhost:5173"])


class Settings(BaseSettings):
    """Composite settings loading from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)
    jira: JiraSettings = Field(default_factory=JiraSettings)
    github: GitHubSettings = Field(default_factory=GitHubSettings)
    pipeline: PipelineSettings = Field(default_factory=PipelineSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls()


# Singleton
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings
