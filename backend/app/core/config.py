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

    # External inference is optional. Categorization can disclose description text;
    # keep it disabled until the operator explicitly enables it.
    CATEGORY_EXTRA_LABELS: list[str] = []
    CATEGORY_KEYWORD_RULES: dict[str, str] = {}
    AI_EXTERNAL_ENABLED: bool = False
    AI_TIMEOUT_SECONDS: float = 10
    AI_MAX_OUTPUT_TOKENS: int = 800

    VECTOR_STORE_PATH: str = "./data/chroma"
    VECTOR_COLLECTION_NAME: str = "zyra_transactions"

    # Notification delivery infrastructure (AI-15M)
    NOTIFICATION_DELIVERY_ENABLED: bool = True
    EMAIL_BACKEND: str = "test"  # "test" or "smtp"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = True
    EMAIL_SENDER_ADDRESS: str = "notifications@porerhishab.com"
    EMAIL_SENDER_NAME: str = "PorerHishab"
    FRONTEND_BASE_URL: str = "http://localhost:5173"
    NOTIFICATION_LEASE_SECONDS: int = 120
    NOTIFICATION_BATCH_SIZE: int = 20
    NOTIFICATION_POLL_SECONDS: float = 5
    NOTIFICATION_RETRY_MAX_DELAY_SECONDS: int = 3600
    NOTIFICATION_RETRY_JITTER_SECONDS: float = 10
    SMTP_TIMEOUT_SECONDS: float = 10
    NOTIFICATION_MAX_RETRIES: int = 3
    NOTIFICATION_RETRY_BACKOFF_SECONDS: list[int] = [60, 300, 900]

    model_config = SettingsConfigDict(env_file=str(ENV_FILE),
                                      env_file_encoding="utf-8",
                                      extra="ignore")


settings = Settings()
