from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AccountBalanceUpdate(BaseModel):
    current_balance: Decimal = Field(decimal_places=2)
    balance_source: str = Field(min_length=1, max_length=30)
    balance_as_of: datetime


class OpeningBalanceUpdate(BaseModel):
    opening_balance: Decimal = Field(decimal_places=2)
    opening_balance_date: date


class AccountBalanceReconciliation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: int
    account_name: str
    currency: str

    reported_balance: Decimal | None
    reported_balance_as_of: datetime | None
    balance_source: str | None

    opening_balance: Decimal | None
    opening_balance_date: date | None

    latest_transaction_date: date | None
    latest_transaction_balance: Decimal | None

    difference: Decimal | None
    derived_balance: Decimal | None

    status: str
    confidence: str

    transaction_count: int
    

    message: str
