import pytest
from types import SimpleNamespace
from datetime import date

@pytest.fixture
def synthetic_digest():
    return SimpleNamespace(local_date=date(2026, 11, 8), total_alerts=1, item_count=1)

@pytest.fixture
def synthetic_digest_items():
    return [SimpleNamespace(severity="high", title="Synthetic title")]

def test_digest_email_does_not_disclose_financial_titles(
    synthetic_digest,
    synthetic_digest_items,
):
    from app.services.notifications.email_content import (
        build_privacy_safe_digest_email,
    )

    secret_title = "ABC Bank Rent BDT 25000"

    synthetic_digest_items[0].title = secret_title

    message = build_privacy_safe_digest_email(
        digest=synthetic_digest,
        items=synthetic_digest_items,
        recipient_email="test@example.com",
    )

    assert secret_title not in message.body_text
    assert secret_title not in message.body_html
    assert "25000" not in message.body_text
    assert "25000" not in message.body_html