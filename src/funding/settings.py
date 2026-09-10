from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FUNDING_", env_file=".env", extra="ignore")
    database_url: str = "sqlite:///data/funding.db"
    source_file: Path = Path("config/sources.json")
    priority_file: Path = Path("config/priorities.json")
    user_agent: str = "MunicipalFundingRegistry/0.4 (public funding monitoring)"
    request_timeout: float = 35
    min_request_interval: float = 0.3
    max_response_bytes: int = 40_000_000
    auth_mode: str = "local"
    entra_tenant_id: str = ""
    entra_audience: str = ""
    azure_sql_server: str = ""
    azure_sql_database: str = "funding"
    managed_identity_client_id: str = ""
    stale_hours: int = 36


def settings() -> Settings:
    return Settings()
