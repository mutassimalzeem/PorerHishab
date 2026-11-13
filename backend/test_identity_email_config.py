"""Synthetic identity/financial transport configuration; never sends email."""
import pytest
from pydantic import ValidationError
from app.core.config import Settings
from app.services.notifications import email_sender as delivery


def config(**overrides):
    values = dict(
        _env_file=None, DATABASE_URL="postgresql+psycopg2://test:test@db/disposable",
        APP_ENV="test", SECRET_KEY="a" * 40, REFRESH_SECRET_KEY="b" * 40, PEPPER="c" * 40,
        CORS_ORIGINS=["https://finance.example"], FRONTEND_BASE_URL="https://finance.example",
        SMTP_HOST="smtp.example.invalid", SMTP_USE_TLS=True, EMAIL_SENDER_ADDRESS="identity@example.invalid",
        EMAIL_BACKEND="test", SECURITY_EMAIL_BACKEND="smtp",
        SECURITY_EMAIL_DELIVERY_ENABLED=True, NOTIFICATION_DELIVERY_ENABLED=False,
    )
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize("identity_enabled", [False, True])
@pytest.mark.parametrize("financial_enabled", [False, True])
@pytest.mark.parametrize("identity_backend", ["test", "smtp"])
@pytest.mark.parametrize("financial_backend", ["test", "smtp"])
def test_independent_development_transports(monkeypatch, identity_enabled, financial_enabled,
                                          identity_backend, financial_backend):
    selected = config(SECURITY_EMAIL_DELIVERY_ENABLED=identity_enabled,
                      NOTIFICATION_DELIVERY_ENABLED=financial_enabled,
                      SECURITY_EMAIL_BACKEND=identity_backend, EMAIL_BACKEND=financial_backend)
    monkeypatch.setattr(delivery, "settings", selected)
    assert isinstance(delivery.get_identity_email_sender(),
                      delivery.SmtpEmailSender if identity_backend == "smtp" else delivery.TestEmailSender)
    assert isinstance(delivery.get_email_sender(),
                      delivery.SmtpEmailSender if financial_backend == "smtp" else delivery.TestEmailSender)


@pytest.mark.parametrize("identity_enabled", [False, True])
@pytest.mark.parametrize("financial_enabled", [False, True])
@pytest.mark.parametrize("identity_backend", ["test", "smtp"])
@pytest.mark.parametrize("financial_backend", ["test", "smtp"])
def test_production_requires_identity_smtp_even_without_financial_email(identity_enabled, financial_enabled,
                                                                       identity_backend, financial_backend):
    values = dict(APP_ENV="production", SECURITY_EMAIL_DELIVERY_ENABLED=identity_enabled,
                  NOTIFICATION_DELIVERY_ENABLED=financial_enabled,
                  SECURITY_EMAIL_BACKEND=identity_backend, EMAIL_BACKEND=financial_backend)
    valid = identity_enabled and identity_backend == "smtp" and (not financial_enabled or financial_backend == "smtp")
    if valid:
        assert config(**values).APP_ENV == "production"
    else:
        with pytest.raises(ValidationError):
            config(**values)


@pytest.mark.parametrize("overrides", [
    {"SMTP_HOST": ""}, {"SMTP_HOST": "localhost"}, {"SMTP_HOST": "127.0.0.1"},
    {"SMTP_USE_TLS": False}, {"SMTP_PORT": 0}, {"SMTP_PORT": 65536},
    {"EMAIL_SENDER_ADDRESS": ""}, {"FRONTEND_BASE_URL": "http://finance.example"},
    {"FRONTEND_BASE_URL": "https://finance.example/#token=bad"},
    {"SMTP_TIMEOUT_SECONDS": 0}, {"SMTP_TIMEOUT_SECONDS": float("inf")},
])
def test_production_missing_identity_configuration_fails_closed(overrides):
    with pytest.raises(ValidationError):
        config(APP_ENV="production", **overrides)


def test_test_adapter_cannot_claim_production_delivery(monkeypatch):
    monkeypatch.setattr(delivery, "settings", config(APP_ENV="production"))
    delivery.TestEmailSender.clear()
    result = delivery.TestEmailSender().send(delivery.EmailMessage(
        "synthetic@example.invalid", "Synthetic", "Synthetic", "<p>Synthetic</p>"))
    assert not result.success and result.failure_category == "configuration"
    assert delivery.TestEmailSender.get_sent_messages() == []


def test_factories_refuse_test_adapters_at_runtime(monkeypatch):
    selected = config(APP_ENV="production")
    # Defense in depth if a setting is mutated after startup validation.
    selected.SECURITY_EMAIL_BACKEND = selected.EMAIL_BACKEND = "test"
    monkeypatch.setattr(delivery, "settings", selected)
    for factory in [delivery.get_identity_email_sender, delivery.get_email_sender]:
        with pytest.raises(ValueError):
            factory()


@pytest.mark.parametrize("overrides", [
    {"REQUEST_MAX_CONCURRENCY": 0}, {"REQUEST_MAX_CONCURRENCY": 257},
    {"REQUEST_BODY_TIMEOUT_SECONDS": 0}, {"REQUEST_BODY_TIMEOUT_SECONDS": float("inf")},
    {"SERVER_LIMIT_CONCURRENCY": 0}, {"SERVER_KEEPALIVE_SECONDS": 0},
])
def test_admission_configuration_rejects_unbounded_values(overrides):
    with pytest.raises(ValidationError):
        config(**overrides)



def test_server_entrypoint_uses_validated_limits(monkeypatch):
    from unittest.mock import Mock
    from app import server
    selected = config(SERVER_LIMIT_CONCURRENCY=37, SERVER_KEEPALIVE_SECONDS=9)
    run = Mock()
    monkeypatch.setattr(server, "settings", selected)
    monkeypatch.setattr(server.uvicorn, "run", run)
    server.main()
    run.assert_called_once_with("app.main:app", host="0.0.0.0", port=8000,
                                limit_concurrency=37, timeout_keep_alive=9,
                                proxy_headers=False, forwarded_allow_ips="")


@pytest.mark.parametrize("peer", ["*", "0.0.0.0/0", "::/0", "untrusted.example", "invalid"])
def test_forwarded_header_trust_cannot_be_unrestricted(peer):
    with pytest.raises(ValidationError):
        config(SERVER_FORWARDED_ALLOW_IPS=peer)


@pytest.mark.parametrize("peer", ["", "127.0.0.1", "::1", "172.24.0.1", "192.0.2.0/28"])
def test_explicit_proxy_peer_configuration(peer):
    assert config(SERVER_FORWARDED_ALLOW_IPS=peer).SERVER_FORWARDED_ALLOW_IPS == peer
