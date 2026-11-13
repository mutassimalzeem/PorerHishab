import os
import ipaddress
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from pydantic import AnyHttpUrl, Field, model_validator

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> <repo root>
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = None if os.getenv("APP_ENV") == "test" else REPO_ROOT / ".env"


class Settings(BaseSettings):
    DATABASE_URL: str

    APP_ENV: Literal["development", "test", "production"] = "development"
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    CORS_ALLOW_CREDENTIALS: bool = True
    SECRET_KEY: str = ""
    REFRESH_SECRET_KEY: str = ""
    PEPPER: str = ""

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # Per process; reject excess requests without waiting or buffering their bodies.
    REQUEST_MAX_CONCURRENCY: int = Field(default=16, ge=1, le=256)
    REQUEST_BODY_TIMEOUT_SECONDS: float = Field(default=15, gt=0, le=300, allow_inf_nan=False)
    SERVER_LIMIT_CONCURRENCY: int = Field(default=50, ge=2, le=1024)
    SERVER_KEEPALIVE_SECONDS: int = Field(default=15, ge=1, le=120)
    # Empty means proxy headers are ignored. Configure only the observed proxy peer.
    SERVER_FORWARDED_ALLOW_IPS: str = ""

    RATE_LIMIT_WINDOW_SECONDS: int = 300
    RATE_LIMIT_MAX_ATTEMPTS: int = 5

    @model_validator(mode="after")
    def validate_deployment(self):
        for peer in self.SERVER_FORWARDED_ALLOW_IPS.split(","):
            if not peer.strip():
                continue
            try:
                network = ipaddress.ip_network(peer.strip(), strict=False)
                if network.prefixlen == 0:
                    raise ValueError
            except ValueError:
                raise ValueError("Trusted proxy peers must be explicit IP addresses or restricted CIDRs")
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
            if not self.SECURITY_EMAIL_DELIVERY_ENABLED or self.SECURITY_EMAIL_BACKEND != "smtp":
                raise ValueError("Production requires SMTP identity email delivery")
            if self.NOTIFICATION_DELIVERY_ENABLED and self.EMAIL_BACKEND != "smtp":
                raise ValueError("Production notifications require SMTP")
            if self.SMTP_HOST.strip().lower() in ("localhost", "127.0.0.1", "::1", ""):
                raise ValueError("Production requires an explicitly configured SMTP provider")
            if not self.SMTP_USE_TLS or not self.EMAIL_SENDER_ADDRESS or "@" not in self.EMAIL_SENDER_ADDRESS:
                raise ValueError("Production SMTP requires TLS and a sender address")
            frontend = urlsplit(self.FRONTEND_BASE_URL)
            if (frontend.scheme != "https" or not frontend.hostname or frontend.username
                    or frontend.password or frontend.query or frontend.fragment):
                raise ValueError("Production requires a public HTTPS frontend URL")
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
    SECURITY_EMAIL_DELIVERY_ENABLED: bool = True
    SECURITY_EMAIL_BACKEND: Literal["test", "smtp"] = "test"
    EMAIL_BACKEND: Literal["test", "smtp"] = "test"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = Field(default=587, ge=1, le=65535)
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
    SMTP_TIMEOUT_SECONDS: float = Field(default=10, gt=0, le=60, allow_inf_nan=False)
    NOTIFICATION_MAX_RETRIES: int = 3
    NOTIFICATION_RETRY_BACKOFF_SECONDS: list[int] = [60, 300, 900]

    model_config = SettingsConfigDict(env_file=ENV_FILE,
                                      env_file_encoding="utf-8",
                                      extra="ignore", hide_input_in_errors=True)


settings = Settings()
