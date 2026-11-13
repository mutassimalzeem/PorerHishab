"""Production configuration boundaries and generic process/database probes."""
from unittest.mock import MagicMock, patch
import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.main import app
from app.api import health


def config(**kwargs):
    values = dict(DATABASE_URL="postgresql+psycopg2://test:test@db/test", _env_file=None)
    values.update(kwargs)
    return Settings(**values)


def production(**kwargs):
    values = dict(APP_ENV="production", CORS_ORIGINS=["https://finance.example"],
        SECRET_KEY="a" * 40, REFRESH_SECRET_KEY="b" * 40, PEPPER="c" * 40,
        NOTIFICATION_DELIVERY_ENABLED=False, SECURITY_EMAIL_DELIVERY_ENABLED=True,
        SECURITY_EMAIL_BACKEND="smtp", EMAIL_BACKEND="test", SMTP_HOST="smtp.example.com",
        FRONTEND_BASE_URL="https://finance.example")
    values.update(kwargs)
    return config(**values)


@pytest.mark.parametrize("origin", ["https://finance.example", "http://localhost:5179", "https://finance.example:8443", "http://[::1]:5173"])
def test_valid_origins(origin):
    assert config(CORS_ORIGINS=[origin]).CORS_ORIGINS == [origin]


@pytest.mark.parametrize("origin", ["*", "https://*.example.com", "null", "file://example.com", "https://example.com/path",
    "https://example.com/", "https://example.com?query", "https://example.com#fragment", "https://user:password@example.com",
    "https://example.com:99999", "https://example.com:0", " https://example.com", "example.com", "https://example.com/../", "https://example.com\\evil", "https://[invalid]"])
def test_invalid_origins(origin):
    with pytest.raises(ValidationError):
        config(CORS_ORIGINS=[origin])


def test_wildcard_only_allowed_without_credentials_in_development():
    assert config(CORS_ORIGINS=["*"], CORS_ALLOW_CREDENTIALS=False).CORS_ORIGINS == ["*"]
    with pytest.raises(ValidationError):
        production(CORS_ORIGINS=["*"], CORS_ALLOW_CREDENTIALS=False)


def test_production_requires_explicit_origins_and_secrets(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    with pytest.raises(ValidationError):
        config(APP_ENV="production", NOTIFICATION_DELIVERY_ENABLED=False)
    for overrides in [
        {"CORS_ORIGINS": []}, {"SECRET_KEY": "change-me"},
        {"PEPPER": ""}, {"REFRESH_SECRET_KEY": "a" * 40},
        {"DATABASE_URL": "sqlite://"}, {"NOTIFICATION_DELIVERY_ENABLED": True},
        {"SECURITY_EMAIL_DELIVERY_ENABLED": False}, {"SECURITY_EMAIL_BACKEND": "test"},
        {"SMTP_HOST": "localhost"}, {"SMTP_USE_TLS": False},
        {"FRONTEND_BASE_URL": "http://finance.example"},
    ]:
        with pytest.raises(ValidationError):
            production(**overrides)
    assert production().APP_ENV == "production"
    valid_smtp_security = production(
        SECURITY_EMAIL_DELIVERY_ENABLED=True,
        NOTIFICATION_DELIVERY_ENABLED=False,
        EMAIL_BACKEND="smtp",
        SMTP_HOST="smtp.example.com",
    )
    assert valid_smtp_security.SECURITY_EMAIL_DELIVERY_ENABLED is True
    assert valid_smtp_security.NOTIFICATION_DELIVERY_ENABLED is False


def test_json_environment_parser_and_invalid_syntax(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", '["https://finance.example"]')
    assert config().CORS_ORIGINS == ["https://finance.example"]
    monkeypatch.setenv("CORS_ORIGINS", "https://one.example,https://two.example")
    with pytest.raises(ValueError):
        config()


def test_validation_errors_hide_input_secrets():
    with pytest.raises(ValidationError) as error:
        production(SECRET_KEY="sensitive-short-value")
    assert "sensitive-short-value" not in str(error.value)


def test_liveness_does_not_contact_database():
    with TestClient(app) as client, patch.object(health.probe_engine, "connect") as connect:
        response = client.get("/health/live")
    assert response.status_code == 200 and response.json() == {"status": "ok"}
    connect.assert_not_called()


def test_readiness_queries_database():
    connection = MagicMock()
    with TestClient(app) as client, patch.object(health.probe_engine, "connect") as connect:
        connect.return_value.__enter__.return_value = connection
        response = client.get("/health/ready")
    assert response.status_code == 200 and response.json() == {"status": "ok"}
    assert str(connection.execute.call_args.args[0]) == "SELECT 1"


def test_readiness_failure_is_generic():
    with TestClient(app) as client, patch.object(health.probe_engine, "connect", side_effect=RuntimeError("password SECRET postgres://private")):
        response = client.get("/health/ready")
    assert response.status_code == 503 and response.json() == {"status": "unavailable"}
    assert "SECRET" not in response.text and "postgres" not in response.text


def test_cors_allows_configured_origin_and_rejects_unknown():
    from app.core.config import settings
    with TestClient(app) as client:
        good = client.options("/health/live", headers={
            "Origin": settings.CORS_ORIGINS[0], "Access-Control-Request-Method": "GET"})
        bad = client.options("/health/live", headers={
            "Origin": "https://untrusted.example", "Access-Control-Request-Method": "GET"})
    assert good.status_code == 200
    assert good.headers["access-control-allow-origin"] == settings.CORS_ORIGINS[0]
    assert bad.status_code == 400 and "access-control-allow-origin" not in bad.headers
