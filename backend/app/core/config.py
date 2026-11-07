from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from pydantic import AnyHttpUrl, model_validator

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> <repo root>
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    DATABASE_URL: str

    APP_ENV: Literal["development", "test", "production"] = "development"
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    CORS_ALLOW_CREDENTIALS: bool = True
    SECRET_KEY: str = ""
    REFRESH_SECRET_KEY: str = ""
    PEPPER: str = ""

    @model_validator(mode="after")
    def validate_deployment(self):
        for origin in self.CORS_ORIGINS:
            if origin == "*":
                if self.CORS_ALLOW_CREDENTIALS or self.APP_ENV == "production":
                    raise ValueError("Wildcard CORS is forbidden with credentials or in production")
                continue
            try:
                AnyHttpUrl(origin)
                parsed = urlsplit(origin)
                port = parsed.port
                valid = (
                    parsed.scheme in ("http", "https") and parsed.hostname
                    and parsed.netloc and not parsed.username and not parsed.password
                    and not parsed.path and not parsed.query and not parsed.fragment
                    and not any(c.isspace() for c in origin) and "*" not in origin and "\\" not in origin
                    and (port is None or 1 <= port <= 65535)
                    and origin == parsed.scheme + "://" + parsed.netloc
                )
            except ValueError:
                valid = False
            if not valid:
                raise ValueError("CORS_ORIGINS must contain HTTP(S) origins without paths or credentials")
        if self.APP_ENV == "production":
            if "CORS_ORIGINS" not in self.model_fields_set or not self.CORS_ORIGINS:
                raise ValueError("Production requires explicit nonempty CORS_ORIGINS")
            if not self.DATABASE_URL.startswith(("postgresql://", "postgresql+psycopg2://")):
                raise ValueError("Production requires PostgreSQL")
            secrets = [self.SECRET_KEY, self.REFRESH_SECRET_KEY, self.PEPPER]
            if any(len(value) < 32 or "change-me" in value.lower() for value in secrets) or len(set(secrets)) != 3:
                raise ValueError("Production requires three distinct secrets of at least 32 characters")
            if self.NOTIFICATION_DELIVERY_ENABLED and (
                self.EMAIL_BACKEND != "smtp" or self.SMTP_HOST in ("localhost", "127.0.0.1", "")
            ):
                raise ValueError("Production delivery requires an explicitly configured SMTP provider")
        return self

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
                                      extra="ignore", hide_input_in_errors=True)


settings = Settings()
