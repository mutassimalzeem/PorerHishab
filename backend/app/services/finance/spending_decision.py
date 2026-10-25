
from decimal import Decimal, ROUND_HALF_UP

from app.schemas.spending_decision import (
    SpendingDecisionRequest,
    SpendingDecisionResponse,
)


MONEY_QUANTUM = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def assess_spending_decision(request: SpendingDecisionRequest) -> SpendingDecisionResponse:
    """Assess whether a purchase preserves the user's requested buffer.

    This is a deterministic balance calculation, not a complete financial
    forecast. It does not infer future income, bills, or unrecorded spending.
    """
    purchase = _money(request.purchase_amount)
    balance = _money(request.starting_balance)
    buffer = _money(request.safety_buffer)

    remaining = _money(balance - purchase)
    above_buffer = _money(max(Decimal("0"), balance - buffer))

    if purchase > balance:
        status = "not_recommended"
        explanation_code = "purchase_exceeds_balance"
        can_afford = False
    elif remaining < buffer:
        status = "caution"
        explanation_code = "purchase_uses_buffer"
        can_afford = False
    else:
        status = "safe"
        explanation_code = "purchase_fits_buffer"
        can_afford = True

    return SpendingDecisionResponse(
        status=status,
        currency="BDT",
        purchase_amount=purchase,
        starting_balance=balance,
        safety_buffer=buffer,
        remaining_after_purchase=remaining,
        amount_available_above_buffer=above_buffer,
        can_afford_without_breaching_buffer=can_afford,
        explanation_code=explanation_code,
        assumptions=[
            "The starting balance was supplied and confirmed by the user.",
            "The balance and purchase amount use the same currency.",
            "No future income, bills, pending transactions, or other purchases are included.",
            "The safety buffer is a user-selected minimum balance, not a personalized financial recommendation.",
        ],
        warnings=[
            "This result considers only the supplied balance, purchase amount, and safety buffer.",
            "A safe result does not guarantee that the purchase is affordable after upcoming obligations.",
        ],
    )
