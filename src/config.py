"""Configuration management for the paper scraping system."""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class SearchConfig(BaseModel):
    """Search configuration."""
    sources: list[str] = ["pubmed", "rss", "biorxiv"]
    journals: list[str] = [
        "Cell", "Nature", "Science",
        "Nature Methods", "Nature Biotechnology"
    ]
    keywords: list[str] = [
        "single-cell RNA-seq", "scRNA-seq",
        "machine learning", "deep learning"
    ]
    max_papers: int = 5
    days_lookback: int = 7


class ScheduleConfig(BaseModel):
    """Schedule configuration."""
    frequency: str = "weekly"  # weekly, monthly
    day: str = "wednesday"


class ClaudeConfig(BaseModel):
    """Claude API configuration."""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096


class OpenAIConfig(BaseModel):
    """OpenAI API configuration."""
    model: str = "gpt-4-turbo-preview"
    max_tokens: int = 4096


class GeminiConfig(BaseModel):
    """Gemini API configuration."""
    model: str = "gemini-2.0-flash-exp"


class AIConfig(BaseModel):
    """AI configuration."""
    llm_provider: str = "claude"  # claude, openai
    summarize_language: str = "korean"
    translate_abstract: bool = True
    generate_summary_image: bool = True
    claude: ClaudeConfig = Field(default_factory=ClaudeConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    gemini: GeminiConfig = Field(default_factory=GeminiConfig)


class ObsidianConfig(BaseModel):
    """Obsidian output configuration."""
    enabled: bool = True
    vault_path: str = "./output/obsidian"


class OutputConfig(BaseModel):
    """Output configuration."""
    pdf_report: bool = True
    obsidian: ObsidianConfig = Field(default_factory=ObsidianConfig)
    reports_path: str = "./output/reports"


class StorageConfig(BaseModel):
    """Storage configuration."""
    history_file: str = "./data/paper_history.json"
    papers_dir: str = "./data/papers"


class AppConfig(BaseModel):
    """Main application configuration."""
    search: SearchConfig = Field(default_factory=SearchConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AppConfig":
        """Load configuration from YAML file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return cls(**data) if data else cls()

    def to_yaml(self, path: str | Path) -> None:
        """Save configuration to YAML file."""
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False, allow_unicode=True)


class EnvConfig(BaseSettings):
    """Environment variables configuration."""

    # API Keys
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")

    # Optional
    pubmed_email: Optional[str] = Field(default=None, alias="PUBMED_EMAIL")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def load_config(config_path: str | Path = "config/config.yaml") -> tuple[AppConfig, EnvConfig]:
    """Load both app config and environment config."""
    app_config = AppConfig.from_yaml(config_path) if Path(config_path).exists() else AppConfig()
    env_config = EnvConfig()
    return app_config, env_config


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


def resolve_path(path: str, base_dir: Optional[Path] = None) -> Path:
    """Resolve a path relative to base directory or project root."""
    p = Path(path)
    if p.is_absolute():
        return p
    base = base_dir or get_project_root()
    return base / p
