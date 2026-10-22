from app.services.finance.evidence import analytics_evidence
from app.services.finance.formatting import format_finance_evidence


def test_format_finance_evidence():
    evidence = [
        analytics_evidence(
            "summary",
            {
                "total_income": "50000.00",
                "total_expenses": "-25000.00",
            },
        )
    ]

    text = format_finance_evidence(evidence)

    assert "[Evidence 1]" in text
    assert "analytics" in text
    assert "summary" in text
    assert "50000.00" in text


def test_empty_evidence():
    assert format_finance_evidence([]) == ""