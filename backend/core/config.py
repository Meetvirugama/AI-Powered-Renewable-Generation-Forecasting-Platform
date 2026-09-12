import yaml
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve project root assuming this file is in backend/core/config.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost:5432/renewable"
    pipeline_api_key: str = "default_pipeline_key"
    groq_api_key: str = ""
    gemini_api_key: str = ""
    dsm_rule_config: str = "config/dsm_rules_2026.yaml"
    s3_bucket_data: str = "default-data-bucket"
    s3_bucket_models: str = "default-models-bucket"
    app_env: str = "development"
    log_level: str = "INFO"
    # Comma-separated browser origins allowed to call this API.
    # Local dev default; the deployed CloudFront domain is added via .env.
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    model_config = SettingsConfigDict(env_file=str(PROJECT_ROOT / ".env"), extra="ignore")

@lru_cache()
def get_settings() -> Settings:
    """Returns cached application settings loaded from environment/.env."""
    return Settings()


def get_cors_origins() -> list[str]:
    """Parse CORS_ORIGINS into a list. '*' allows any origin (local dev only)."""
    raw = get_settings().cors_origins.strip()
    if raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]

def load_yaml(path: str) -> dict:
    """Loads a YAML file given a path relative to the project root and returns its dictionary representation."""
    full_path = PROJECT_ROOT / path
    with open(full_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_plants_config(path: str = "config/plants.yaml") -> list[dict]:
    """Loads and returns the list of plant configurations."""
    data = load_yaml(path)
    return data.get("plants", [])

def load_settings_config(path: str = "config/settings.yaml") -> dict:
    """Loads the main application settings from a YAML file."""
    return load_yaml(path)

def load_dsm_rules(path: str) -> dict:
    """Loads DSM rules configuration from a YAML file."""
    return load_yaml(path)
