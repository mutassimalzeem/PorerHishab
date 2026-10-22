from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> <repo root>
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    DATABASE_URL: str

    OPENAI_KEY: str | None = None
    # Any OpenAI-compatible endpoint (e.g. https://aihub.071129.xyz/v1).
    # Leave unset to talk to https://api.openai.com/v1.
    OPENAI_BASE_URL: str | None = None
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    # OpenAI accepts pre-tokenized input, most OpenAI-compatible gateways do not.
    # Set to false when pointing OPENAI_BASE_URL at a third-party provider.
    OPENAI_EMBEDDING_CHECK_CTX_LENGTH: bool = True
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"

    VECTOR_STORE_PATH: str = "./data/chroma"
    VECTOR_COLLECTION_NAME: str = "zyra_transactions"

    model_config = SettingsConfigDict(env_file=str(ENV_FILE),
                                      env_file_encoding="utf-8",
                                      extra="ignore")


settings = Settings()

