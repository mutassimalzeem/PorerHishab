
"""Authenticated purchase-affordability assessment endpoint."""

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.spending_decision import (
    SpendingDecisionRequest,
    SpendingDecisionResponse,
)
from app.services.finance.spending_decision import (
    assess_spending_decision,
)

router = APIRouter(prefix="/finance", tags=["finance"])


@router.post("/spending-decision", response_model=SpendingDecisionResponse)
def spending_decision(
    payload: SpendingDecisionRequest,
    current: User = Depends(get_current_user)) -> SpendingDecisionResponse:
    """Assess a purchase against the authenticated user's supplied balance.

    The user must supply their available balance and desired safety buffer.
    This endpoint does not read or modify account balances or transactions.
    """
    # Authentication is enforced by the dependency above.
    # The assessment uses only the explicit values in this request.
    return assess_spending_decision(payload)
