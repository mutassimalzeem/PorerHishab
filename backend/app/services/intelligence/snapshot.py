"""The structured financial snapshot the intelligence engine produces (AI-13).

A snapshot keeps four kinds of information separate — raw coverage, observed
facts, scheduled (planned) figures and estimates/forecasts — so consumers can
never silently replace an observation with an estimate:

* ``MonthlyHistory``: totals for the complete prior months, plus the
  coach-style average baseline *estimate* derived from the existing
  deterministic forecasting service;
* ``ScheduledObligations``: planned income/expense totals with the horizon's
  inclusive window and the rule that scheduled income never counts as
  available money;
* ``FinancialSnapshot``: one as-of view combining current-month observed
  totals, category facts, recurring patterns, obligations, active goals and
  explicit limitations.

Nothing here calls a provider: every value is SQL-decided and deterministic
in ``(database state, as_of)``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.models.savings_goal import SavingsGoal
from app.services.analytics.insights import detect_recurring_transactions
from app.services.forecasting.cashflow import calculate_cashflow_forecast
from app.services.intelligence.coverage import (
    DataCoverage,
    assess_coverage,
)
from app.services.intelligence.facts import (
    LIMITATIONS,
    grouped_expenses,
    scheduled_cashflow_items,
    scoped,
    scheduled_totals,
    totals,
)
from app.services.intelligence.periods import (
    DEFAULT_HISTORY_MONTHS,
    DEFAULT_UPCOMING_HORIZON_DAYS,
    Period,
    current_month_period,
    history_window_period,
    month_end,
    month_key,
    upcoming_period,
)

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class MonthlyHistory:
    """Observed totals for complete prior months plus a baseline estimate.

    ``baseline`` reuses the existing deterministic cashflow forecast service
    exactly as the coach does: monthly aggregate pairs are fed as records and
    the service computes simple monthly averages, never a projected bank
    balance.
    """

    period: Period                        # the complete-month window
    monthly: list[dict]                   # coach-shaped totals dicts per month
    months_with_records: tuple[str, ...]  # YYYY-MM keys with >= 1 record
    adequate: bool                        # every history month has records
    baseline: dict                        # forecast-service result (an estimate)
    coverage: dict                        # union-window Coverage dict (coach shape)

    def to_dict(self) -> dict:
        return {
            "period": self.period.to_dict(),
            "monthly": self.monthly,
            "adequate": self.adequate,
            "baseline": self.baseline,
            "coverage": self.coverage,
        }


def _first_day(month: str) -> date:
    year, month_number = (int(part) for part in month.split("-"))
    return date(year, month_number, 1)


def monthly_history(
    db: Session,
    user_id: int,
    as_of: date,
    months: int = DEFAULT_HISTORY_MONTHS,
) -> MonthlyHistory:
    """Complete prior months of observed totals (dates inclusive).

    A history month counts as observed when it has at least one record;
    amounts of empty months stay unknown (``None``), never zero.
    """
    period = history_window_period(as_of, months)
    monthly: list[dict] = []
    months_with_records: list[str] = []
    for key in period.month_keys:
        first_day = _first_day(key)
        values = totals(db, user_id, first_day, month_end(first_day))
        monthly.append(values)
        if values["coverage"]["transaction_count"] > 0:
            months_with_records.append(key)

    adequate = all(
        values["coverage"]["transaction_count"] > 0 for values in monthly)
    baseline = baseline_forecast(monthly, as_of)
    union = totals(db, user_id, period.start, period.end)

    return MonthlyHistory(
        period=period,
        monthly=monthly,
        months_with_records=tuple(months_with_records),
        adequate=adequate,
        baseline=baseline,
        coverage=union["coverage"],
    )


def baseline_forecast(monthly_totals: list[dict], as_of: date) -> dict:
    """Monthly-average estimate fed through the existing forecast service.

    Only months with recorded income contribute records, matching the
    original coach behaviour. A month with income but no recorded expenses
    contributes an income-only record (expenses treated as zero) instead of
    crashing on a missing amount.
    """
    records: list[SimpleNamespace] = []
    for values in monthly_totals:
        if values["income"] is None:
            continue
        last_day = date.fromisoformat(values["coverage"]["end_date"])
        records.append(SimpleNamespace(date=last_day, amount=values["income"]))
        if values["expenses"] is not None:
            records.append(
                SimpleNamespace(date=last_day, amount=-values["expenses"]))
    return calculate_cashflow_forecast(
        records, ZERO, months_ahead=1, as_of_date=as_of)


@dataclass(frozen=True)
class ScheduledObligations:
    """Planned (not yet paid) cashflow rows inside an inclusive horizon.

    ``expense_total`` is a known plan to reserve against; ``income_total`` is
    deliberately uncertain and must never be added to available money.
    """

    period: Period
    expense_total: Decimal
    income_total: Decimal
    items: list[dict] = field(default_factory=list)
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "period": self.period.to_dict(),
            "scheduled_expenses": str(self.expense_total),
            "uncertain_scheduled_income": str(self.income_total),
            "items": [
                {
                    "scheduled_item_id": item["scheduled_item_id"],
                    "title": item["title"],
                    "kind": item["kind"],
                    "amount": str(item["amount"]),
                    "due_date": item["due_date"].isoformat(),
                    "record_type": item["record_type"],
                }
                for item in self.items
            ],
            "limitations": list(self.limitations),
        }


def scheduled_obligations(
    db: Session,
    user_id: int,
    as_of: date,
    days: int = DEFAULT_UPCOMING_HORIZON_DAYS,
) -> ScheduledObligations:
    """Scheduled plans due in the next ``days`` days; paid/cancelled excluded."""
    period = upcoming_period(as_of, days)
    expense_total, income_total = scheduled_totals(db, user_id, period.start, period.end)
    items = [
        {
            "scheduled_item_id": item.id,
            "title": item.title,
            "kind": item.kind,
            "amount": item.amount,
            "due_date": item.due_date,
            "record_type": "plan",
        }
        for item in scheduled_cashflow_items(db, user_id, period.start, period.end)
    ]
    return ScheduledObligations(
        period=period,
        expense_total=expense_total,
        income_total=income_total,
        items=items,
        limitations=(
            "Scheduled income is uncertain and is displayed separately, "
            "never added to projected balances.",
            "Paid and cancelled plans are excluded; paid plans never become "
            "actual transactions.",
        ),
    )


@dataclass
class FinancialSnapshot:
    """One user's observed financial position as of a fixed date."""

    user_id: int                          # internal only; not serialized below
    as_of: date
    period: Period                        # current month to date
    history: MonthlyHistory
    history_coverage: DataCoverage
    coverage: DataCoverage                # current-window coverage statement
    income: Decimal | None
    expenses: Decimal | None
    net_cashflow: Decimal | None
    category_spending: list[dict]
    recurring_patterns: list[dict]
    scheduled_obligations: ScheduledObligations
    goals: list[dict]

    @property
    def is_history_adequate(self) -> bool:
        return self.history.adequate

    @property
    def scheduled_cashflow_available(self) -> bool:
        """Whether scheduled-cashflow plans exist to reason about."""
        return bool(self.scheduled_obligations.items) or (
            self.scheduled_obligations.expense_total > 0
            or self.scheduled_obligations.income_total > 0
        )

    @property
    def limitations(self) -> list[str]:
        limitations = list(LIMITATIONS)
        limitations.extend(self.history_coverage.limitations)
        limitations.extend(self.coverage.limitations)
        return limitations

    def to_dict(self) -> dict:
        """Frontend-friendly shape; observed vs estimated is explicit."""
        return {
            "as_of_date": self.as_of.isoformat(),
            "period": self.period.to_dict(),
            "data_coverage": self.history_coverage.to_dict(),
            "current_period_coverage": self.coverage.to_dict(),
            "income": None if self.income is None else str(self.income),
            "expenses": None if self.expenses is None else str(self.expenses),
            "net_cashflow": None if self.net_cashflow is None else str(self.net_cashflow),
            "value_kind": "observed",
            "category_spending": [
                {
                    "category": row["category"],
                    "expenses": str(row["expenses"]),
                    "transaction_count": row["transaction_count"],
                }
                for row in self.category_spending
            ],
            "recurring_patterns": [
                {
                    "merchant": row["merchant"],
                    "occurrences": row["occurrences"],
                    "months": row["months"],
                    "median_amount": str(row["median_amount"]),
                    "total_spent": str(row["total_spent"]),
                    "first_date": str(row["first_date"]),
                    "last_date": str(row["last_date"]),
                }
                for row in self.recurring_patterns
            ],
            "scheduled_cashflow_available": self.scheduled_cashflow_available,
            "scheduled_obligations": self.scheduled_obligations.to_dict(),
            "history": {
                "period": self.history.period.to_dict(),
                "adequate": self.history.adequate,
                "baseline": self.history.baseline,
            },
            "goals": [
                {
                    "goal_id": goal["goal_id"],
                    "name": goal["name"],
                    "target_amount": str(goal["target_amount"]),
                    "current_saved": None if goal["current_saved"] is None
                    else str(goal["current_saved"]),
                    "target_date": goal["target_date"].isoformat(),
                    "status": goal["status"],
                }
                for goal in self.goals
            ],
            "limitations": self.limitations,
        }


def build_snapshot(
    db: Session,
    user_id: int,
    as_of: date | None = None,
    history_months: int = DEFAULT_HISTORY_MONTHS,
) -> FinancialSnapshot:
    """Build the snapshot with fixed windows from central period helpers."""
    from app.services.intelligence.periods import today_dhaka

    as_of = as_of or today_dhaka()
    period = current_month_period(as_of)

    history = monthly_history(db, user_id, as_of, months=history_months)
    history_coverage = assess_coverage(
        history.period, history.months_with_records, as_of,
        required_complete_months=len(history.period.month_keys),
    )

    current = totals(db, user_id, period.start, period.end)
    current_month_observed = (
        [month_key(as_of)]
        if current["coverage"]["transaction_count"] > 0 else []
    )
    coverage = assess_coverage(period, current_month_observed, as_of)

    rows = scoped(db, user_id, history.period.start, history.period.end).all()
    recurring = detect_recurring_transactions(rows)
    obligations = scheduled_obligations(db, user_id, as_of)
    goals = [
        {
            "goal_id": goal.id,
            "name": goal.name,
            "target_amount": goal.target_amount,
            "current_saved": goal.current_saved,
            "target_date": goal.target_date,
            "status": goal.status,
        }
        for goal in db.query(SavingsGoal).filter(
            SavingsGoal.user_id == user_id,
            SavingsGoal.status == "active",
        ).order_by(SavingsGoal.target_date, SavingsGoal.id).all()
    ]

    return FinancialSnapshot(
        user_id=user_id,
        as_of=as_of,
        period=period,
        history=history,
        history_coverage=history_coverage,
        coverage=coverage,
        income=current["income"],
        expenses=current["expenses"],
        net_cashflow=current["net"],
        category_spending=grouped_expenses(
            db, user_id, period.start, period.end, limit=1000),
        recurring_patterns=recurring,
        scheduled_obligations=obligations,
        goals=goals,
    )
