from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> <repo root>
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    DATABASE_URL: str

    model_config = SettingsConfigDict(env_file=str(ENV_FILE),
                                      env_file_encoding="utf-8",
                                      extra="ignore")


settings = Settings()
