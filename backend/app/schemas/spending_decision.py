from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SpendingStatus = Literal["safe", "caution", "not_recommended", "insufficient_data"]

class SpendingDecisionRequest(BaseModel):
    """Input for a deterministic purchase-affordability assessment"""

    model_config = ConfigDict(extra= "forbid")

    purchase_amount: Decimal = Field(gt = 0, description= "Proposed purchase amount in BDT (Bangladeshi Taka).")
    starting_balance: Decimal = Field(ge = 0, description= "User confirmed available balance in BDT before the purchase.")

    safety_buffer: Decimal= Field(ge = 0, description= "Minimum balance the user wants to preserve, in BDT.")



class SpendingDecisionResponse(BaseModel):
    """Explainable result of a purchase-affordablity assessment"""

    model_config = ConfigDict(extra= "forbid")

    status: SpendingStatus
    currency: str = "BDT"

    purchase_amount: Decimal
    starting_balance: Decimal
    safety_buffer: Decimal
    remaining_after_purchase: Decimal
    amount_available_above_buffer: Decimal

    can_afford_without_breaching_buffer: bool
    explanation_code: Literal[
        "purchase_fits_buffer",
        "purchase_uses_buffer",
        "purchase_exceeds_balance",
        "invalid_financial_context",
    ]

    assumptions: list[str]
    warnings: list[str]