from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "StatementGraph Cards"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False

    postgres_dsn: str = Field(default="sqlite+pysqlite:///./statementgraph.db")
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = Field(default="")

    secret_key: str = Field(default="")
    max_upload_size_mb: int = 25
    upload_dir: str = "uploads"
    data_pdf_path: str = "../data/bank_statements.pdf"

    allowed_origins: str | list[str] = ["http://localhost:5173"]
    trusted_hosts: str | list[str] = ["localhost", "127.0.0.1", "testserver"]

    duplicate_window_minutes: int = 30
    burst_window_hours: int = 3
    burst_threshold: int = 3

    @field_validator("allowed_origins", "trusted_hosts", mode="before")
    @classmethod
    def _parse_csv_list(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return value
        return [item.strip() for item in value.split(",") if item.strip()]

    @field_validator("max_upload_size_mb")
    @classmethod
    def _validate_upload_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_upload_size_mb must be greater than zero")
        return value

    def ensure_upload_dir(self) -> Path:
        """Ensure upload directory exists and return path."""

        path = Path(self.upload_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()
