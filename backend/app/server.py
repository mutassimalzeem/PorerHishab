"""Deployment entry point: validated, configurable Uvicorn admission limits."""
import uvicorn
from app.core.config import settings


def main():
    uvicorn.run(
        "app.main:app", host="0.0.0.0", port=8000,
        limit_concurrency=settings.SERVER_LIMIT_CONCURRENCY,
        timeout_keep_alive=settings.SERVER_KEEPALIVE_SECONDS,
        proxy_headers=bool(settings.SERVER_FORWARDED_ALLOW_IPS.strip()),
        forwarded_allow_ips=settings.SERVER_FORWARDED_ALLOW_IPS,
    )


if __name__ == "__main__":
    main()
