"""Deterministic financial signals with structured evidence (AI-13).

A signal is a structured, explainable observation about one user's own
records. Signals carry:

* typed identity including a **stable id** built from stable properties
  (type, category/record identity, period) rather than random UUIDs, so the
  same facts produce the same id and notification/insight lifecycles can
  dedupe on it. No raw internal user id appears in externally visible ids;
* separate ``observed``/``reference`` values with delta and percentage
  change — ``None``, never fabricated, when a baseline is missing;
* an explicit estimate flag: savings-estimate and projected-shortfall
  values are labeled ``estimate`` so wording layers can't present them as
  observed facts;
* evidence maps holding the exact structural keys the existing coaching
  contract exposes.

Thresholds are the product's existing constants, extracted here verbatim so
the same rules can never drift between surfaces.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from hashlib import sha256

from sqlalchemy.orm import Session

from app.models.scheduled_cashflow_item import ScheduledCashflowItem
from app.services.intelligence.categories import (
    percentage_change,
)
from app.services.intelligence.facts import (
    grouped_expenses,
    scheduled_cashflow_items,
    totals,
)
from app.services.intelligence.goals import GoalAssessment, goal_assessment
from app.services.intelligence.periods import (
    DEFAULT_UPCOMING_HORIZON_DAYS,
    Period,
    latest_complete_month_period,
    money,
    month_shift,
    previous_complete_month_period,
    current_month_period,
)

# -- signal types (identifiers are stable API) --------------------------------
SIGNAL_UNUSUAL_SPENDING = "unusual_spending"
SIGNAL_SAVINGS_OPPORTUNITY = "savings_opportunity"
SIGNAL_UPCOMING_EXPENSE = "upcoming_expense"
SIGNAL_PROJECTED_SHORTFALL = "projected_shortfall"
SIGNAL_GOAL_PROGRESS = "goal_progress"

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

# -- product constants (preserved from the coach contract) ---------------------
#: Categories the product treats as worth reviewing when spending increases.
REDUCIBLE_CATEGORIES = frozenset(
    {"Food", "Shopping", "Entertainment", "Subscription", "Travel"})
#: A category fires when latest spending exceeds the prior month by > 10%.
INCREASE_FACTOR = Decimal("1.10")
#: Suggested reduction estimate: at most 10% of the latest month's spending.
REDUCTION_FRACTION = Decimal("0.10")
#: Unusual spending: current month-to-date exceeds the largest prior month × 1.5.
UNUSUAL_FACTOR = Decimal("1.5")
#: Upcoming-obligation horizon in days.
UPCOMING_HORIZON_DAYS = DEFAULT_UPCOMING_HORIZON_DAYS

PERCENT_SCALE = Decimal("0.01")


def stable_category_token(category: str) -> str:
    """Deterministic opaque token for a category name (original scheme)."""
    return sha256(category.encode()).hexdigest()[:12]


@dataclass
class FinancialSignal:
    """One structured, evidence-backed financial observation."""

    signal_type: str
    severity: str
    stable_id: str
    observed_period: Period
    comparison_period: Period | None
    observed_value: Decimal | None
    reference_value: Decimal | None
    delta: Decimal | None
    percentage_change: Decimal | None
    evidence: dict
    estimate: bool
    estimate_label: str                    # "observed" | "estimate"
    subject: str | None = None             # category / goal name, when typed
    limitations: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "signal_type": self.signal_type,
            "severity": self.severity,
            "stable_id": self.stable_id,
            "subject": self.subject,
            "observed_period": self.observed_period.to_dict(),
            "comparison_period": None if self.comparison_period is None
            else self.comparison_period.to_dict(),
            "observed_value": None if self.observed_value is None
            else str(self.observed_value),
            "reference_value": None if self.reference_value is None
            else str(self.reference_value),
            "delta": None if self.delta is None else str(self.delta),
            "percentage_change": None if self.percentage_change is None
            else str(self.percentage_change),
            "estimate": self.estimate,
            "estimate_label": self.estimate_label,
            "evidence": self.evidence,
            "assumptions": list(self.assumptions),
            "limitations": list(self.limitations),
        }


def _observed_signal(**kwargs) -> FinancialSignal:
    return FinancialSignal(estimate=False, estimate_label="observed", **kwargs)


def _estimated_signal(**kwargs) -> FinancialSignal:
    return FinancialSignal(estimate=True, estimate_label="estimate", **kwargs)


# -- savings opportunity (category increase) -----------------------------------


def savings_opportunity_signals(
    db: Session,
    user_id: int,
    as_of: date,
    history_adequate: bool,
    comparison_basis: dict[str, Decimal],
) -> list[FinancialSignal]:
    """Category-increase signals over the latest complete month.

    The estimate is ``min(latest × 10%, latest − previous)``: an optional
    reduction, never a guaranteed saving, and computed only when the
    comparison month actually observed the category.
    """
    if not history_adequate:
        return []
    latest = latest_complete_month_period(as_of)
    previous = previous_complete_month_period(as_of, back=2)
    latest_rows = {
        row["category"]: row
        for row in grouped_expenses(db, user_id, latest.start, latest.end,
                                    limit=1000)
    }
    signals: list[FinancialSignal] = []
    for category, row in latest_rows.items():
        if category not in REDUCIBLE_CATEGORIES:
            continue
        current_spending = row["expenses"]
        prior = comparison_basis.get(category)
        if prior is None or prior <= 0:
            continue
        if current_spending <= prior * INCREASE_FACTOR:
            continue
        saving = money(min(current_spending * REDUCTION_FRACTION,
                           current_spending - prior))
        if saving <= 0:
            continue
        evidence = {
            "period_start": latest.start,
            "period_end": latest.end,
            "category": category,
            "latest_expenses": current_spending,
            "previous_expenses": prior,
            "estimated_monthly_saving": saving,
            "increase_factor": str(INCREASE_FACTOR),
            "reduction_fraction": str(REDUCTION_FRACTION),
        }
        signals.append(_estimated_signal(
            signal_type=SIGNAL_SAVINGS_OPPORTUNITY,
            severity=SEVERITY_INFO,
            stable_id=(
                f"review-category:{latest.start:%Y-%m}:"
                f"{stable_category_token(category)}"),
            observed_period=latest,
            comparison_period=previous,
            observed_value=current_spending,
            reference_value=prior,
            delta=current_spending - prior,
            percentage_change=percentage_change(current_spending, prior),
            evidence=evidence,
            subject=category,
            limitations=[
                "Estimated saving assumes similar spending in both months and "
                "is not guaranteed or necessarily feasible.",
            ],
            assumptions=[
                "Consider a reduction of up to 10% only if feasible; essential needs come first.",
                "Annual impact assumes the same optional reduction for twelve months; it is not guaranteed.",
            ],
        ))
    signals.sort(key=lambda signal: (-signal.evidence["estimated_monthly_saving"],
                                     signal.stable_id))
    return signals


# -- unusual spending -----------------------------------------------------------


def unusual_spending_signal(
    db: Session,
    user_id: int,
    as_of: date,
    history_adequate: bool,
    history_monthly_expenses: list[Decimal],
) -> FinancialSignal | None:
    """Fires when month-to-date spending exceeds the prior ceiling by > 50%.

    Partial months inflate easily, so the signal compares against the largest
    *complete* prior month and always says so through its period evidence.
    """
    if not history_adequate:
        return None
    period = current_month_period(as_of)
    current = totals(db, user_id, period.start, period.end)
    current_expenses = current["expenses"]
    if current_expenses is None:
        return None
    ceiling = max(
        (value or Decimal("0.00") for value in history_monthly_expenses),
        default=Decimal("0.00"))
    if ceiling <= 0 or not current_expenses > ceiling * UNUSUAL_FACTOR:
        return None
    return _observed_signal(
        signal_type=SIGNAL_UNUSUAL_SPENDING,
        severity=SEVERITY_WARNING,
        stable_id=f"unusual-spending:{as_of:%Y-%m}",
        observed_period=period,
        comparison_period=None,
        observed_value=current_expenses,
        reference_value=ceiling,
        delta=current_expenses - ceiling,
        percentage_change=percentage_change(current_expenses, ceiling),
        evidence={
            "current_expenses": current_expenses,
            "largest_prior_month": ceiling,
            "unusual_factor": str(UNUSUAL_FACTOR),
        },
        limitations=[
            "The current month is incomplete; a large recorded amount may be "
            "a timing artefact rather than a change in habits.",
        ],
    )


# -- upcoming scheduled obligation ----------------------------------------------


def upcoming_expense_signals(
    db: Session,
    user_id: int,
    as_of: date,
    days: int = UPCOMING_HORIZON_DAYS,
) -> list[FinancialSignal]:
    """Planned, unpaid expenses inside the horizon (plans, not actuals)."""
    period = Period(kind="upcoming_horizon", start=as_of,
                    end=as_of + timedelta(days=days), is_complete=False,
                    label=f"next {days} days")
    items = scheduled_cashflow_items(
        db, user_id, period.start, period.end, kind="expense", limit=20)
    signals: list[FinancialSignal] = []
    for item in items:
        signals.append(_observed_signal(
            signal_type=SIGNAL_UPCOMING_EXPENSE,
            severity=SEVERITY_WARNING,
            stable_id=f"scheduled-expense:{item.id}:{item.due_date}",
            observed_period=Period(
                kind="plan_window", start=as_of, end=item.due_date,
                is_complete=False, label=f"plan due {item.due_date.isoformat()}"),
            comparison_period=None,
            observed_value=item.amount,
            reference_value=None,
            delta=None,
            percentage_change=None,
            evidence={
                "scheduled_item_id": item.id,
                "title": item.title,
                "amount": item.amount,
                "record_type": "plan",
            },
            subject=item.title,
            limitations=[
                "This is a scheduled plan, not an actual transaction; "
                "unrecorded bills are unknown.",
            ],
        ))
    return signals


# -- projected shortfall ---------------------------------------------------------


def projected_shortfall_signal(
    as_of: date,
    history_adequate: bool,
    baseline_average_monthly_net: Decimal | None,
) -> FinancialSignal | None:
    """Historical-average deficit estimate over the next calendar month."""
    if not history_adequate or baseline_average_monthly_net is None:
        return None
    if not baseline_average_monthly_net < 0:
        return None
    horizon_end = month_shift(as_of, 1) - timedelta(days=1)
    return _estimated_signal(
        signal_type=SIGNAL_PROJECTED_SHORTFALL,
        severity=SEVERITY_WARNING,
        stable_id=f"estimated-deficit:{as_of:%Y-%m}",
        observed_period=Period(
            kind="forecast_horizon", start=as_of, end=horizon_end,
            is_complete=False, label=f"estimate for month starting {month_shift(as_of, 1).isoformat()}"),
        comparison_period=None,
        observed_value=baseline_average_monthly_net,
        reference_value=None,
        delta=None,
        percentage_change=None,
        evidence={
            "estimated_monthly_net": baseline_average_monthly_net,
            "is_estimate": True,
        },
        limitations=[
            "Historical averages suggest a deficit; this is not a predicted "
            "bank balance.",
        ],
        assumptions=[
            "The estimate uses simple monthly averages from complete prior "
            "months and no future income or seasonal patterns.",
        ],
    )


# -- goal progress -----------------------------------------------------------------


def goal_progress_signals(
    db: Session,
    user_id: int,
    as_of: date,
    history: dict | None,
) -> list[FinancialSignal]:
    """One progress signal per active goal (ordered oldest target first)."""
    from app.models.savings_goal import SavingsGoal

    goals = db.query(SavingsGoal).filter(
        SavingsGoal.user_id == user_id,
        SavingsGoal.status == "active",
    ).order_by(SavingsGoal.target_date, SavingsGoal.id).limit(20).all()
    signals: list[FinancialSignal] = []
    for goal in goals:
        assessment = goal_assessment(db, user_id, goal, as_of, history)
        signals.append(_observed_signal(
            signal_type=SIGNAL_GOAL_PROGRESS,
            severity=SEVERITY_WARNING if assessment.is_concerning else SEVERITY_INFO,
            stable_id=f"goal-progress:{goal.id}:{as_of:%Y-%m}",
            observed_period=Period(
                kind="goal_horizon", start=as_of, end=goal.target_date,
                is_complete=False, label=f"towards {goal.name}"),
            comparison_period=None,
            observed_value=goal.current_saved,
            reference_value=goal.target_amount,
            delta=None if goal.current_saved is None
            else money(goal.target_amount - goal.current_saved),
            percentage_change=None,
            evidence={
                "goal_id": goal.id,
                "name": goal.name,
                "saved_source": "user_reported",
                "current_saved": goal.current_saved,
                "affordability": assessment.affordability,
            },
            subject=goal.name,
            limitations=list(assessment.limitations),
            assumptions=[
                "Saved amounts are user-reported and not reconciled with account balances.",
            ],
        ))
    return signals


# -- aggregate --------------------------------------------------------------------


def build_signals(
    db: Session,
    user_id: int,
    as_of: date,
    history,
) -> list[FinancialSignal]:
    """All engine signals for one user, deterministic in (state, as_of).

    ``history`` is the coach-shaped
    :class:`~app.services.intelligence.snapshot.MonthlyHistory` payload so
    history work is not repeated.
    """
    from app.services.intelligence.categories import comparison_expenses_by_category

    signals: list[FinancialSignal] = []
    monthly_expenses = [
        values["expenses"] for values in history.monthly
    ]
    baseline = history.baseline
    signals.extend(savings_opportunity_signals(
        db, user_id, as_of, history.adequate,
        comparison_expenses_by_category(
            db, user_id, previous_complete_month_period(as_of, back=2)),
    ))
    unusual = unusual_spending_signal(
        db, user_id, as_of, history.adequate, monthly_expenses)
    if unusual is not None:
        signals.append(unusual)
    signals.extend(upcoming_expense_signals(db, user_id, as_of))
    shortfall = projected_shortfall_signal(
        as_of, history.adequate, baseline.get("average_monthly_net"))
    if shortfall is not None:
        signals.append(shortfall)
    signals.extend(goal_progress_signals(db, user_id, as_of, {
        "adequate": history.adequate,
        "baseline": baseline,
    }))
    return signals
