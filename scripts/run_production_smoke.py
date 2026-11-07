"""Validate production Compose locally with synthetic secrets and an isolated volume."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import urllib.error
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    project = "porerhishab-prod-smoke-" + uuid4().hex[:12]
    assert project.startswith("porerhishab-prod-smoke-") and project.replace("-", "").isalnum()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix=project) as temporary:
        env_path = Path(temporary) / "production.env"
        password = secrets.token_hex(24)
        values = {
            "PRODUCTION_ENV_FILE": env_path.as_posix(),
            "APP_IMAGE": project + ":test",
            "APP_ENV": "production",
            "POSTGRES_DB": "smoke", "POSTGRES_USER": "smoke",
            "POSTGRES_PASSWORD": password,
            "DATABASE_URL": f"postgresql+psycopg2://smoke:{password}@db:5432/smoke",
            "SECRET_KEY": secrets.token_hex(32), "REFRESH_SECRET_KEY": secrets.token_hex(32),
            "PEPPER": secrets.token_hex(32), "CORS_ORIGINS": "'[\"https://frontend.example\"]'",
            "FRONTEND_BASE_URL": "https://frontend.example", "API_PORT": str(port),
            "NOTIFICATION_DELIVERY_ENABLED": "false", "EMAIL_BACKEND": "test",
            "AI_EXTERNAL_ENABLED": "false",
        }
        env_path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
        if os.name != "nt":
            env_path.chmod(0o600)
        # Shell environment overrides --env-file. Remove relevant inherited values
        # so this smoke test cannot accidentally select operator credentials/volumes.
        env = {k: v for k, v in os.environ.items() if k not in values and not k.startswith("COMPOSE_")}
        base = ["docker", "compose", "--env-file", str(env_path), "-p", project,
                "-f", str(ROOT / "docker-compose.prod.yml")]
        def run(*args, capture=False):
            return subprocess.run([*base, *args], cwd=ROOT, env=env, check=True,
                                  capture_output=capture, text=True)
        try:
            run("config", "--quiet")  # Never print the resolved secret-bearing configuration.
            run("build", "api")
            run("up", "-d", "--wait", "db")
            run("run", "--rm", "migrate")
            run("up", "-d", "--wait", "api")
            def get(path):
                with urllib.request.urlopen(f"http://127.0.0.1:{port}" + path, timeout=10) as response:
                    return json.load(response)
            assert get("/health/live") == {"status": "ok"}
            assert get("/health/ready") == {"status": "ok"}
            request = urllib.request.Request(f"http://127.0.0.1:{port}/health/live", method="OPTIONS",
                headers={"Origin": "https://frontend.example", "Access-Control-Request-Method": "GET"})
            with urllib.request.urlopen(request, timeout=10) as response:
                assert response.headers["Access-Control-Allow-Origin"] == "https://frontend.example"
            run("up", "-d", "worker")
            run("exec", "-T", "worker", "python", "-m", "app.services.notifications.worker", "--once")
            services = run("ps", "--format", "json", capture=True).stdout
            # Compose versions emit either JSON lines or an array.
            try:
                rows = json.loads(services)
                rows = rows if isinstance(rows, list) else [rows]
            except json.JSONDecodeError:
                rows = [json.loads(line) for line in services.splitlines() if line.strip()]
            assert any(row["Service"] == "worker" and row["State"] == "running" for row in rows)
            run("stop", "db")
            assert get("/health/live") == {"status": "ok"}
            try:
                get("/health/ready")
                raise AssertionError("Readiness succeeded with PostgreSQL stopped")
            except urllib.error.HTTPError as error:
                assert error.code == 503
                assert json.load(error) == {"status": "unavailable"}
            run("stop", "worker")
            print("Production smoke passed: build, config, clean migration, API/CORS, worker start/shutdown, database-failure readiness")
        finally:
            # Only this generated test project's containers and volume are removed.
            run("down", "--volumes", "--remove-orphans")


if __name__ == "__main__":
    main()
