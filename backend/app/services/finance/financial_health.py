"""AI-15O: explainable normalization of authoritative facts, never an LLM.

All thresholds are application UX choices, not validated financial standards.
See docs/ai-15o-financial-health.md for denominators and overlap boundaries.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from app.models.financial_health import FinancialHealthSnapshot
from app.models.savings_goal import SavingsGoal
from app.models.scheduled_cashflow_item import ScheduledCashflowItem
from app.models.user import User
from app.schemas.financial_health import FinancialHealthComponent, FinancialHealthEvidence, FinancialHealthProfile, FinancialHealthTrend
from app.services.finance.account_position import get_account_overview
from app.services.finance.obligations import obligation_amounts_for_items
from app.services.finance.runway import financial_runway
from app.services.intelligence.periods import today_dhaka
from app.services.intelligence.snapshot import monthly_history

D = Decimal
ZERO = D("0")
HUNDRED = D("100")
HEALTH_CALCULATION_VERSION = "ai-15o-v1"
COMPONENT_WEIGHTS = dict.fromkeys(("cashflow_stability", "liquidity", "obligation_pressure", "spending_stability", "account_reliability", "savings_progress", "financial_stress"), D("1"))
STATUS_THRESHOLDS = ((D("80"), "strong"), (D("60"), "stable"), (D("40"), "watch"), (ZERO, "strained"))
MIN_HISTORY_MONTHS = 3  # complete observed months, consistent with AI-13/15D
BALANCE_MAX_AGE_DAYS = 30  # health requires recent verified cash, not live-bank claims
HORIZON_DAYS = 30
STRESS_WINDOW_DAYS = 90
TREND_MIN_DAYS = 7
QUALITY_PARTIAL_MIN = D("40")
QUALITY_GOOD_MIN = D("70")
TREND_CHANGE_POINTS = D("3")  # smaller changes are displayed as stable
# Cashflow: -20% margin -> 0, break-even -> 50, +20% margin -> 100.
CASHFLOW_MARGIN_SCALE = D("250")
# Liquidity: cash covering >=3 times the conservative 30-day reserve -> 100.
LIQUIDITY_RESERVE_MULTIPLE = D("3")
# Spending: only repeated (>50%) growth relative to the same first month is pressure.
SPENDING_GROWTH_THRESHOLD = D("1.5")
REPEATED_SPENDING_SCORE = D("40")
MISMATCH_RELIABILITY_SCORE = D("40")
# Distinct overdue dates: one -> 70, two -> 40, >=4 -> 0.
OVERDUE_DATE_PENALTY = D("30")
BASE_LIMITATIONS = [
    "Application-specific diagnostic; not a credit score or universal measure of financial health.",
    "Observed BDT records and schedules may be incomplete; unknown information is never treated as healthy.",
    "Goal savings are self-reported; score changes do not establish causation.",
]
EXPLANATIONS = {
    "cashflow_stability": "Based on the average recorded income surplus margin across three complete months.",
    "liquidity": "Based on recent verified cash relative to the runway service's conservative near-term expense reserve.",
    "obligation_pressure": "Based on known remaining upcoming obligations relative to recent verified cash; uncertain income is excluded.",
    "spending_stability": "Only repeated spending growth across complete months is flagged; an isolated large purchase is not penalized.",
    "account_reliability": "Based on observed reconciliation conflicts; missing verification reduces coverage rather than financial condition.",
    "savings_progress": "Based on reported progress towards configured goals; absence of goals is unknown.",
    "financial_stress": "Based on distinct overdue dates with remaining obligations; this describes observable pressure, not emotions.",
}
MISSING = {
    "cashflow_stability": "Three complete months with recorded positive income are required.",
    "liquidity": "Recent verified cash for every BDT account and an adequate historical runway are required.",
    "obligation_pressure": "Recent verified cash and recorded expense schedules are required.",
    "spending_stability": "Three complete months with recorded spending are required.",
    "account_reliability": "All BDT accounts require recent verification or an observable reconciliation conflict.",
    "savings_progress": "Configured goals with explicitly reported savings are required.",
    "financial_stress": "Recorded expense schedules are required to observe overdue payment pressure.",
}


def rounded(value):
    return value.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def clamp(value):
    return rounded(max(ZERO, min(HUNDRED, value)))


def classify(score):
    if score is None:
        return "insufficient_data"
    return next(label for threshold, label in STATUS_THRESHOLDS if score >= threshold)


def component(key, score=None, evidence=(), metadata=None):
    score = clamp(score) if score is not None else None
    return FinancialHealthComponent(key=key, score=score, status=classify(score),
        data_available=score is not None,
        explanation=EXPLANATIONS[key] if score is not None else MISSING[key],
        evidence=list(evidence), limitations=[] if score is not None else [MISSING[key]],
        calculation_metadata={"weight": str(COMPONENT_WEIGHTS[key]), **(metadata or {})})


def aggregate(components, as_of, observed_at=None):
    available = [c for c in components if c.data_available and c.score is not None]
    weight = sum((COMPONENT_WEIGHTS[c.key] for c in available), ZERO)
    coverage = rounded(HUNDRED * weight / sum(COMPONENT_WEIGHTS.values(), ZERO))
    overall = rounded(sum((c.score * COMPONENT_WEIGHTS[c.key] for c in available), ZERO) / weight) if weight else None
    quality = "insufficient" if not available else "limited" if coverage < QUALITY_PARTIAL_MIN else "partial" if coverage < QUALITY_GOOD_MIN else "good" if coverage < HUNDRED else "high"
    return FinancialHealthProfile(overall_score=overall, status=classify(overall), coverage_percent=coverage,
        available_components=[c.key for c in available], missing_components=[c.key for c in components if not c.data_available],
        data_quality_status=quality, limitations=BASE_LIMITATIONS + [x for c in components for x in c.limitations],
        components=components, calculation_version=HEALTH_CALCULATION_VERSION, as_of_date=as_of, observed_at=observed_at)


def gather_profile(db, user_id, *, as_of=None, observed_at=None):
    as_of = as_of or today_dhaka()
    observed_at = observed_at or datetime.now(timezone.utc)
    history = monthly_history(db, user_id, as_of, months=MIN_HISTORY_MONTHS, exclude_transfers=True)
    accounts = get_account_overview(db, user_id, as_of=as_of)
    runway = financial_runway(db, user_id, as_of=as_of, horizon_days=HORIZON_DAYS, history=history, account_overview=accounts)
    schedules = db.query(ScheduledCashflowItem).filter(
        ScheduledCashflowItem.user_id == user_id, ScheduledCashflowItem.kind == "expense",
        ScheduledCashflowItem.status != "cancelled",
        ScheduledCashflowItem.due_date >= as_of - timedelta(days=STRESS_WINDOW_DAYS),
        ScheduledCashflowItem.due_date <= as_of + timedelta(days=HORIZON_DAYS)).all()
    amounts = obligation_amounts_for_items(db, user_id, schedules)
    goals = db.query(SavingsGoal).filter(SavingsGoal.user_id == user_id, SavingsGoal.status.in_(("active", "completed"))).all()
    def ev(metric, value, unit, source, financial_date=as_of):
        return FinancialHealthEvidence(metric=metric, value=value, unit=unit, source=source, as_of_date=financial_date, observed_at=observed_at)
    result = {key: component(key) for key in COMPONENT_WEIGHTS}
    rows = history.monthly
    if history.adequate and all(row["income"] is not None and row["income"] > ZERO and row["expenses"] is not None and row["expenses"] > ZERO for row in rows):
        margins = [row["net"] / row["income"] for row in rows]
        margin = sum(margins, ZERO) / D(len(margins))
        result["cashflow_stability"] = component("cashflow_stability", D("50") + margin * CASHFLOW_MARGIN_SCALE,
            [ev("mean_surplus_margin", margin, "ratio", "monthly_history", history.period.end)],
            {"formula": "clamp(50 + 250 * mean monthly net/income)", "months": str(MIN_HISTORY_MONTHS)})
    bdt = [a for a in accounts.items if a.currency == "BDT"]
    def recent(account):
        timestamp = account.balance_as_of
        if timestamp is None:
            return False
        day = timestamp.astimezone(ZoneInfo("Asia/Dhaka")).date() if isinstance(timestamp, datetime) and timestamp.tzinfo else timestamp.date() if isinstance(timestamp, datetime) else timestamp
        return 0 <= (as_of - day).days <= BALANCE_MAX_AGE_DAYS
    verified = bool(bdt) and all(a.position_status == "trusted" and recent(a) for a in bdt)
    trusted = accounts.trusted_bdt_position.total if verified else None
    known_accounts = bool(bdt) and all((a.position_status == "trusted" and recent(a)) or a.position_status == "unreconciled" and a.reconciliation.difference is not None for a in bdt)
    if known_accounts:
        conflicts = sum(a.position_status == "unreconciled" for a in bdt)
        result["account_reliability"] = component("account_reliability", MISMATCH_RELIABILITY_SCORE if conflicts else HUNDRED,
            [ev("reconciliation_conflicts", conflicts, "accounts", "account_position"), ev("verified_accounts", sum(a.position_status == "trusted" for a in bdt), "accounts", "account_position")])
    if trusted is not None and runway.runway_status != "insufficient_data" and runway.expected_expense_reserve is not None and runway.expected_expense_reserve > ZERO:
        # Only use a complete trusted position, never a partial account sum.
        reserve = runway.expected_expense_reserve
        result["liquidity"] = component("liquidity", trusted / (reserve * LIQUIDITY_RESERVE_MULTIPLE) * HUNDRED,
            [ev("trusted_cash", trusted, "BDT", "account_position"), ev("expected_expense_reserve", reserve, "BDT", "financial_runway")],
            {"formula": "clamp(trusted_cash / (3 * runway reserve) * 100)", "horizon_days": str(HORIZON_DAYS)})
    if trusted is not None and schedules:
        reserve = runway.scheduled_expense_reserve
        score = HUNDRED * (D("1") - reserve / trusted) if trusted > ZERO else ZERO
        # Zero cash + zero obligations has no meaningful denominator.
        if trusted > ZERO or reserve > ZERO or trusted < ZERO:
            result["obligation_pressure"] = component("obligation_pressure", score,
                [ev("upcoming_remaining_obligations", reserve, "BDT", "financial_runway"), ev("trusted_cash", trusted, "BDT", "account_position")],
                {"formula": "clamp(100 * (1 - upcoming reserve / trusted cash)); nonpositive cash -> 0"})
    if history.adequate and all(row["expenses"] is not None and row["expenses"] > ZERO for row in rows):
        spending = [row["expenses"] for row in rows]
        repeated = all(v > spending[0] * SPENDING_GROWTH_THRESHOLD for v in spending[1:])
        result["spending_stability"] = component("spending_stability", REPEATED_SPENDING_SCORE if repeated else HUNDRED,
            [ev("monthly_expenses_" + str(i + 1), value, "BDT", "monthly_history", date.fromisoformat(rows[i]["coverage"]["end_date"])) for i, value in enumerate(spending)],
            {"formula": "40 if both later months exceed first month's spending by >50%; otherwise 100"})
    if goals and all(g.current_saved is not None and g.target_amount > ZERO for g in goals):
        # Normalize the model's reported progress; do not infer savings from account cash.
        progress = sum((min(D("1"), g.current_saved / g.target_amount) for g in goals), ZERO) / D(len(goals))
        result["savings_progress"] = component("savings_progress", HUNDRED * progress,
            [ev("mean_reported_goal_progress", progress, "ratio", "savings_goals"), ev("configured_goals", len(goals), "goals", "savings_goals")],
            {"formula": "mean(min(reported_saved / target, 1)) * 100; no inference about contribution history"})
    if schedules:
        overdue_dates = {s.due_date for s in schedules if s.due_date < as_of and amounts[s.id].reserved_amount > ZERO}
        result["financial_stress"] = component("financial_stress", HUNDRED - D(len(overdue_dates)) * OVERDUE_DATE_PENALTY,
            [ev("overdue_dates_with_remaining_obligations", len(overdue_dates), "dates", "obligation_reconciliation")],
            {"formula": "clamp(100 - 30 * distinct overdue dates)", "window_days": str(STRESS_WINDOW_DAYS)})
    profile = aggregate(list(result.values()), as_of, observed_at)
    profile.limitations += ["No recorded overdue dates means no observed overdue pressure, not proof that all bills are known.", "Runway and upcoming-obligation components share known commitments for distinct cash-resilience and commitment-pressure views; their correlation is a model limitation.", "Action completion, coaching, alerts and notification counts do not change scores; they can repeat the same underlying signal."]
    if not verified:
        profile.limitations.append("Account balances are missing, unverified, stale or conflicting; partial trusted cash is not substituted.")
    return profile


def history_profiles(db, user_id, *, from_date=None, to_date=None, limit=90):
    query = db.query(FinancialHealthSnapshot).filter(FinancialHealthSnapshot.user_id == user_id)
    if from_date:
        query = query.filter(FinancialHealthSnapshot.snapshot_date >= from_date)
    if to_date:
        query = query.filter(FinancialHealthSnapshot.snapshot_date <= to_date)
    # Return the most recent bounded window in chronological order.
    rows = query.order_by(FinancialHealthSnapshot.snapshot_date.desc(), FinancialHealthSnapshot.observed_at.desc(), FinancialHealthSnapshot.id.desc()).limit(limit).all()
    return [FinancialHealthProfile.model_validate(row.profile) for row in reversed(rows)]


def trend_from_profiles(profiles, *, days=90):
    trend = FinancialHealthTrend(period=f"{days}d")
    if not profiles:
        return trend
    latest = profiles[-1]
    candidates = [p for p in profiles[:-1] if latest.as_of_date - timedelta(days=days) <= p.as_of_date <= latest.as_of_date - timedelta(days=TREND_MIN_DAYS)
        and p.calculation_version == latest.calculation_version
        and p.schema_version == latest.schema_version
        and set(p.available_components) == set(latest.available_components)
        and p.overall_score is not None and latest.overall_score is not None]
    if not candidates:
        return trend
    previous = candidates[0]
    change = latest.overall_score - previous.overall_score
    def direction(delta):
        return "improving" if delta >= TREND_CHANGE_POINTS else "declining" if delta <= -TREND_CHANGE_POINTS else "stable"
    old = {c.key: c for c in previous.components}
    trend.direction, trend.change = direction(change), change
    trend.confidence = "adequate" if latest.coverage_percent >= QUALITY_GOOD_MIN else "limited"
    trend.current_date, trend.comparison_date = latest.as_of_date, previous.as_of_date
    trend.components = {c.key: direction(c.score - old[c.key].score) if c.score is not None and c.key in old and old[c.key].score is not None else "insufficient_data" for c in latest.components}
    return trend


def get_trend(db, user_id, days=90):
    profiles = history_profiles(db, user_id, limit=1000)
    return trend_from_profiles(profiles, days=days)


def current_profile(db, user_id):
    rows = history_profiles(db, user_id, limit=1)
    if not rows:
        return aggregate([component(key) for key in COMPONENT_WEIGHTS], today_dhaka())
    profile = rows[-1]
    profile.trend = get_trend(db, user_id)
    return profile


def evaluate(db, user_id, *, as_of=None):
    # Same lock convention as AI-15L. Lock before gathering so same-user requests serialize.
    db.query(User).filter(User.id == user_id).with_for_update().one()
    profile = gather_profile(db, user_id, as_of=as_of)
    existing = db.query(FinancialHealthSnapshot).filter_by(user_id=user_id,
        snapshot_date=profile.as_of_date, calculation_version=HEALTH_CALCULATION_VERSION).one_or_none()
    row = existing or FinancialHealthSnapshot(user_id=user_id, snapshot_date=profile.as_of_date)
    row.observed_at = profile.observed_at
    row.overall_score, row.status = profile.overall_score, profile.status
    row.coverage_percent, row.data_quality_status = profile.coverage_percent, profile.data_quality_status
    row.schema_version, row.calculation_version = profile.schema_version, profile.calculation_version
    row.profile = profile.model_dump(mode="json")
    db.add(row)
    db.flush()
    profile.trend = get_trend(db, user_id)
    db.commit()
    return profile
