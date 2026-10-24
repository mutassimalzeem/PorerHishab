
import pytest
from pydantic import ValidationError

from app.schemas.financial_insights import (
    FinancialInsight,
    FinancialInsights,
)
from app.services.ai.financial_insights import _prepare_analytics


def test_financial_insight_schema_accepts_valid_insight():
    result = FinancialInsight(
        type="spending_increase",
        severity="warning",
        title="Spending increased",
        message="Your spending increased compared with the previous month.",
        metric="25%",
        category="Food",
    )

    assert result.type == "spending_increase"
    assert result.severity == "warning"
    assert result.metric == "25%"


def test_financial_insight_schema_rejects_unknown_type():
    with pytest.raises(ValidationError):
        FinancialInsight(
            type="made_up_type",
            severity="warning",
            title="Invalid insight",
            message="This insight uses an unsupported type.",
        )


def test_financial_insights_defaults_to_empty_list():
    result = FinancialInsights()

    assert result.insights == []


def test_financial_insights_rejects_more_than_ten_items():
    insight = FinancialInsight(
        type="budget_signal",
        severity="info",
        title="Budget baseline",
        message="Your observed spending provides a starting budget baseline.",
    )

    with pytest.raises(ValidationError):
        FinancialInsights(insights=[insight] * 11)


def test_prepare_analytics_includes_only_allowed_fields():
    analytics = {
        "summary": {"total_income": "50000.00"},
        "month_over_month": [{"expense_change_pct": "0.2500"}],
        "categories": {"expenses_by_category": {"Food": "-10000.00"}},
        "raw_transactions": [{"description": "Private transaction detail"}],
        "internal_debug": "should not be passed",
    }

    from app.services.ai.financial_insights import _prepare_analytics

    result = _prepare_analytics(analytics)

    assert "summary" in result
    assert "month_over_month" in result
    assert "categories" in result
    assert "raw_transactions" not in result
    assert "internal_debug" not in result
    assert "Private transaction detail" not in result
