"""The financial-intelligence engine entry point (AI-13).

The engine turns one authenticated user's raw financial records into:

1. a :class:`~app.services.intelligence.snapshot.FinancialSnapshot`
   (observed facts, coverage, scheduled plans, goals);
2. an optional :class:`~app.services.intelligence.cashflow.CashflowIntelligence`
   that keeps actual, scheduled and forecast values distinct with exposed
   assumptions;
3. deterministic
   :class:`~app.services.intelligence.signals.FinancialSignal` objects with
   structured evidence and stable ids.

It is deliberately *not* an LLM component: the engine must work with no
model, no network and no optional AI dependency, so arithmetic and facts stay
deterministic while wording layers (chat, AI insights) merely explain the
structured output.

Layers (never blurred)::

    raw records -> engine (facts) -> observed snapshot
                 -> engine (rules) -> signals (+estimates)
                 -> consumers      -> wording / rendering only
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.services.intelligence.coverage import DataCoverage
from app.services.intelligence.facts import scheduled_totals, totals
from app.services.intelligence.periods import (
    Period,
    month_shift,
    month_start,
    today_dhaka,
)
from app.services.intelligence.signals import (
    FinancialSignal,
    build_signals,
)
from app.services.intelligence.snapshot import (
    FinancialSnapshot,
    MonthlyHistory,
    scheduled_obligations,
)
from app.services.intelligence.snapshot import build_snapshot

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class CashflowIntelligence:
    """Actual, scheduled and forecast cashflow kept strictly distinct.

    ``forecast_*`` values are monthly-average *estimates* from the existing
    deterministic forecasting service; ``scheduled_income`` is never added to
    any projected balance; ``actual_*`` sums are observed records only.
    """

    as_of: date
    actual_window: Period
    actual_income: Decimal | None
    actual_expense: Decimal | None
    scheduled_horizon: Period
    scheduled_expense: Decimal
    scheduled_income: Decimal
    forecast_income: Decimal | None
    forecast_expense: Decimal | None
    forecast_net: Decimal | None
    forecast_status: str | None
    assumptions: list[str]
    limitations: list[str]

    @property
    def estimated(self) -> bool:
        """True whenever any projected value is present."""
        return self.forecast_income is not None or self.forecast_net is not None

    def to_dict(self) -> dict:
        return {
            "type": "forecast",
            "as_of_date": self.as_of.isoformat(),
            "actual_window": self.actual_window.to_dict(),
            "actual_income": None if self.actual_income is None else str(self.actual_income),
            "actual_expense": None if self.actual_expense is None else str(self.actual_expense),
            "scheduled_horizon": self.scheduled_horizon.to_dict(),
            "scheduled_expense": str(self.scheduled_expense),
            "scheduled_income": str(self.scheduled_income),
            "forecast_income": None if self.forecast_income is None else str(self.forecast_income),
            "forecast_expense": None if self.forecast_expense is None else str(self.forecast_expense),
            "forecast_net": None if self.forecast_net is None else str(self.forecast_net),
            "forecast_status": self.forecast_status,
            "estimated": self.estimated,
            "assumptions": list(self.assumptions),
            "limitations": list(self.limitations),
        }


def build_cashflow_intelligence(
    db: Session,
    user_id: int,
    as_of: date | None = None,
    history: MonthlyHistory | None = None,
) -> CashflowIntelligence:
    """Actuals to date, plans in the horizon, and the monthly-average estimate."""
    from app.services.intelligence.snapshot import monthly_history as build_history

    as_of = as_of or today_dhaka()
    history = history or build_history(db, user_id, as_of)

    actual_window = Period(
        kind="actual_window", start=history.period.start, end=as_of,
        is_complete=False,
        label=f"history to date ({history.period.start.isoformat()} to {as_of.isoformat()})")
    actual = totals(db, user_id, actual_window.start, actual_window.end)
    horizon = Period(
        kind="scheduled_horizon", start=month_start(as_of),
        end=month_shift(as_of, 1) - timedelta(days=1),
        is_complete=False,
        label=f"current month plus commitments to {month_shift(as_of, 1) - timedelta(days=1)}",
    )
    scheduled_expense, scheduled_income = scheduled_totals(
        db, user_id, horizon.start, horizon.end)
    adequate = history.adequate
    baseline = history.baseline

    assumptions = list(baseline.get("assumptions") or [])
    limitations = [
        "Actual values come from imported records and may be incomplete.",
        "Scheduled income is uncertain and is never added to projected balances.",
    ]
    if not adequate:
        limitations.append(
            "Insufficient history: only the known-obligations scenario is available.")

    return CashflowIntelligence(
        as_of=as_of,
        actual_window=actual_window,
        actual_income=actual["income"],
        actual_expense=actual["expenses"],
        scheduled_horizon=horizon,
        scheduled_expense=scheduled_expense,
        scheduled_income=scheduled_income,
        forecast_income=baseline["average_monthly_income"] if adequate else None,
        forecast_expense=baseline["average_monthly_expenses"] if adequate else None,
        forecast_net=baseline["average_monthly_net"] if adequate else None,
        forecast_status=baseline.get("status"),
        assumptions=assumptions,
        limitations=limitations,
    )


@dataclass
class FinancialIntelligence:
    """Everything the engine exposes for one user at one as-of date."""

    user_id: int
    as_of: date
    snapshot: FinancialSnapshot
    signals: list[FinancialSignal]
    cashflow: CashflowIntelligence

    @property
    def observed_and_estimated(self) -> dict:
        """Convenience view separating observed facts from estimates."""
        return {
            "observed": {
                "income": self.snapshot.income,
                "expenses": self.snapshot.expenses,
                "net_cashflow": self.snapshot.net_cashflow,
            },
            "estimated": {
                "cashflow": self.cashflow.to_dict(),
            },
        }

    def to_dict(self) -> dict:
        return {
            "as_of_date": self.as_of.isoformat(),
            "snapshot": self.snapshot.to_dict(),
            "cashflow": self.cashflow.to_dict(),
            "signals": [signal.to_dict() for signal in self.signals],
            "limitations": self.snapshot.limitations,
        }


def build_financial_intelligence(
    db: Session,
    user_id: int,
    as_of: date | None = None,
    *,
    include_signals: bool = True,
    history_months: int = 3,
) -> FinancialIntelligence:
    """Run the full engine for one authenticated user (deterministic).

    The same database state with the same ``as_of`` produces equivalent
    intelligence, byte-for-byte at the serialization boundary.
    """
    as_of = as_of or today_dhaka()
    snapshot = build_snapshot(db, user_id, as_of, history_months=history_months)
    history = snapshot.history
    signals = build_signals(db, user_id, as_of, history) if include_signals else []
    cashflow = build_cashflow_intelligence(
        db, user_id, as_of, history=history)
    return FinancialIntelligence(
        user_id=user_id,
        as_of=as_of,
        snapshot=snapshot,
        signals=signals,
        cashflow=cashflow,
    )
