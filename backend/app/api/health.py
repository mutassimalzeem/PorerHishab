"""Generic process and PostgreSQL reachability probes; no infrastructure disclosure."""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text, create_engine
from sqlalchemy.pool import NullPool
from app.core.config import settings
# No pool checkout wait; each probe has bounded PostgreSQL connect/statement time.
probe_engine = create_engine(settings.DATABASE_URL, poolclass=NullPool,
    connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"}
    if settings.DATABASE_URL.startswith("postgresql") else {})

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live():
    return {"status": "ok"}


@router.get("/ready")
def ready():
    try:
        # Use a dedicated short-timeout connection, outside request transactions.
        with probe_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}
