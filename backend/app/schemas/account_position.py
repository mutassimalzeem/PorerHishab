from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


AccountPositionStatus = Literal[
    "trusted",
    "reported",
    "derived",
    "unreconciled",
    "stale",
    "insufficient_data",
    "unsupported_currency",
]

TrustedPositionStatus = Literal[
    "trusted",
    "partially_trusted",
    "needs_review",
    "unavailable",
]


class AccountReconciliationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    confidence: str
    derived_balance: Decimal | None = None
    difference: Decimal | None = None
    message: str | None = None
    transaction_count: int = 0
    latest_transaction_date: date | None = None


class AccountPositionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source: str | None = None
    account_type: str
    currency: str

    current_balance: Decimal | None = None
    balance_source: str | None = None
    balance_as_of: datetime | None = None

    opening_balance: Decimal | None = None
    opening_balance_date: date | None = None

    position_status: AccountPositionStatus
    is_eligible_for_bdt_aggregate: bool
    reconciliation: AccountReconciliationSummary


class TrustedBdtPosition(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total: Decimal | None = None
    eligible_accounts_count: int
    review_accounts_count: int
    excluded_accounts_count: int
    status: TrustedPositionStatus
    currency: Literal["BDT"] = "BDT"
    message: str
    contributing_account_names: list[str] = Field(default_factory=list)


class AccountOverviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[AccountPositionItem]
    trusted_bdt_position: TrustedBdtPosition


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    source: str | None = Field(default=None, max_length=50)
    account_type: str = Field(default="cash", max_length=50)
    currency: str = Field(default="BDT", min_length=3, max_length=3)
    current_balance: Decimal | None = None
    balance_source: str | None = Field(default=None, max_length=30)
    balance_as_of: datetime | None = None
    opening_balance: Decimal | None = None
    opening_balance_date: date | None = None
