"""Own a disposable PostgreSQL container and normal FastAPI/browser processes."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
import argparse

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-tests", nargs="*", default=None,
                        help="Also run selected backend tests (no paths means the full backend suite).")
    args = parser.parse_args()
    # Fail before creating resources if a fixed test port is already occupied.
    for port in [55439, 8019, 5179]:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    env = {**os.environ, "DATABASE_URL": "postgresql+psycopg2://review_e2e:review_e2e@127.0.0.1:55439/porerhishab_review_e2e",
           "REVIEW_E2E_DISPOSABLE": "1", "AI_EXTERNAL_ENABLED": "false", "OPENAI_KEY": "",
           "SECRET_KEY": "disposable-review-access", "REFRESH_SECRET_KEY": "disposable-review-refresh",
           "PEPPER": "disposable-review-pepper", "NOTIFICATION_DELIVERY_ENABLED": "false"}
    name = "porerhishab-review-e2e-" + uuid.uuid4().hex[:12]
    backend = None

    def run(args, extra_env=None):
        subprocess.run(args, cwd=ROOT, env={**env, **(extra_env or {})}, check=True)

    try:
        run(["docker", "run", "--detach", "--rm", "--name", name,
             "-p", "127.0.0.1:55439:5432", "-e", "POSTGRES_USER=review_e2e",
             "-e", "POSTGRES_PASSWORD=review_e2e", "-e", "POSTGRES_DB=porerhishab_review_e2e",
             "--tmpfs", "/var/lib/postgresql/data", "postgres:16"])
        for attempt in range(60):
            ready = subprocess.run(["docker", "exec", name, "pg_isready", "-U", "review_e2e"], capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("PostgreSQL readiness timed out")
        run([sys.executable, "-m", "alembic", "upgrade", "head"])
        if args.backend_tests is not None:
            run([sys.executable, "-m", "pytest", *(args.backend_tests or ["backend"]), "-q", "--tb=short"],
                extra_env={"NOTIFICATION_DELIVERY_ENABLED": "true", "EMAIL_BACKEND": "test"})
        run([sys.executable, "scripts/seed_financial_review_e2e.py"])
        run([sys.executable, "scripts/seed_financial_review_e2e.py"])
        backend = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", "backend",
                                    "--host", "127.0.0.1", "--port", "8019"], cwd=ROOT, env=env)
        for attempt in range(60):
            if backend.poll() is not None:
                raise RuntimeError("FastAPI exited before readiness")
            try:
                with urllib.request.urlopen("http://127.0.0.1:8019/openapi.json", timeout=2):
                    break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError("FastAPI readiness timed out")
        run([sys.executable, "scripts/check_notification_delivery_e2e.py"],
            extra_env={"NOTIFICATION_DELIVERY_ENABLED": "true", "EMAIL_BACKEND": "test"})
        subprocess.run(["npm.cmd" if os.name == "nt" else "npm", "exec", "--", "playwright", "test",
                        "--config", "playwright.real-api.config.ts"], cwd=ROOT / "frontend", env=env, check=True)
    finally:
        try:
            if backend is not None:
                backend.terminate()
                try:
                    backend.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    backend.kill()
                    backend.wait(timeout=5)
        finally:
            subprocess.run(["docker", "rm", "--force", name], check=False)


if __name__ == "__main__":
    main()
