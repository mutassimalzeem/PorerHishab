
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.spending_decision import SpendingDecisionRequest
from app.services.finance.spending_decision import assess_spending_decision


def make_request(purchase: str, balance: str, buffer: str) -> SpendingDecisionRequest:

    return SpendingDecisionRequest(
        purchase_amount=Decimal(purchase),
        starting_balance=Decimal(balance),
        safety_buffer=Decimal(buffer),
    )


def test_purchase_fits_above_safety_buffer():

    result = assess_spending_decision(
        make_request("2000", "10000", "3000"))

    assert result.status == "safe"
    assert result.remaining_after_purchase == Decimal("8000.00")
    assert result.amount_available_above_buffer == Decimal("7000.00")
    assert result.can_afford_without_breaching_buffer is True
    assert result.explanation_code == "purchase_fits_buffer"


def test_purchase_exactly_preserves_safety_buffer():
    result = assess_spending_decision(
        make_request("7000", "10000", "3000")
    )

    assert result.status == "safe"
    assert result.remaining_after_purchase == Decimal("3000.00")


def test_purchase_breaches_safety_buffer():
    result = assess_spending_decision(
        make_request("8000", "10000", "3000")
    )

    assert result.status == "caution"
    assert result.remaining_after_purchase == Decimal("2000.00")
    assert result.can_afford_without_breaching_buffer is False
    assert result.explanation_code == "purchase_uses_buffer"


def test_purchase_exceeds_balance():
    result = assess_spending_decision(
        make_request("12000", "10000", "1000")
    )

    assert result.status == "not_recommended"
    assert result.remaining_after_purchase == Decimal("-2000.00")
    assert result.explanation_code == "purchase_exceeds_balance"


def test_zero_balance_and_zero_buffer():
    result = assess_spending_decision(
        make_request("0.01", "0", "0")
    )

    assert result.status == "not_recommended"


def test_money_is_rounded_half_up():
    result = assess_spending_decision(
        make_request("10.005", "100.005", "20.00")
    )

    assert result.purchase_amount == Decimal("10.01")
    assert result.starting_balance == Decimal("100.01")
    assert result.remaining_after_purchase == Decimal("90.00")


@pytest.mark.parametrize(
    ("purchase", "balance", "buffer"),
    [
        ("0", "100", "10"),
        ("-1", "100", "10"),
        ("1", "-1", "0"),
        ("1", "100", "-1"),
    ],
)
def test_invalid_inputs_are_rejected(purchase, balance, buffer):
    with pytest.raises(ValidationError):
        make_request(purchase, balance, buffer)


def test_extra_request_fields_are_rejected():
    with pytest.raises(ValidationError):
        SpendingDecisionRequest(
            purchase_amount=Decimal("10"),
            starting_balance=Decimal("100"),
            safety_buffer=Decimal("20"),
            future_salary=Decimal("5000"),
        )
