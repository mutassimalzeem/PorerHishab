"""Recommendation evaluation dataset (AI-12D).

Covers the two savings-recommendation surfaces:

* the deterministic savings plan (``app.services.planning.savings``) and its
  per-category ``suggested_cut`` entries;
* the coach's spending-reduction opportunities
  (``app.services.finance.coach.recommendations``).

Cases are scored on *structured financial properties* — grounding,
arithmetic, estimate labeling, no double counting, personalization, and data
sufficiency — never on string equality of the phrasing.  All pinned numbers
are re-derived from the blueprint with plain arithmetic by
:func:`recommendation_ground_truth_consistency`.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP

from app.evaluation.datasets.finance_scenario import (
    AS_OF, ScenarioTransaction,
)

RECOMMENDATION_AS_OF = AS_OF  # 2026-10-25

#: Configured tolerance for "observed spending x reduction fraction ~= estimate".
ARITHMETIC_TOLERANCE = Decimal("0.01")

PLAN_REDUCTION_FRACTION = Decimal("0.20")
COACH_REDUCTION_FRACTION = Decimal("0.10")
COACH_INCREASE_FACTOR = Decimal("1.10")
REDUCIBLE_CATEGORIES = frozenset(
    {"Food", "Shopping", "Entertainment", "Subscription", "Travel"})

RECOMMENDATION_ISOLATION_CANARY_MERCHANT = "CANARY PRIVATE LEDGER"
RECOMMENDATION_ISOLATION_MARKERS = (RECOMMENDATION_ISOLATION_CANARY_MERCHANT, "777777")


def money(value) -> Decimal:
    """Money rounding copied from the coach contract (half-up, 2 dp)."""
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _plan_round(value) -> Decimal:
    """The plan module uses ``quantize`` without an explicit rounding mode."""
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


# ---------------------------------------------------------------------------
# Scenario worlds
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecommendationScenario:
    user_key: str
    transactions: tuple[ScenarioTransaction, ...]
    history_months: int = 3          # complete calendar months with records


def _tx(iso: str, amount: str, category: str, merchant: str) -> ScenarioTransaction:
    return ScenarioTransaction(date.fromisoformat(iso), amount, category, merchant)


def _salary_month(year: int, month: int, amount: str) -> ScenarioTransaction:
    return _tx(f"{year}-{month:02d}-05", amount, "Salary", "Acme Corp Payroll")


def plan_scenario(user_key: str, salary: str, categories: dict[str, str]) -> RecommendationScenario:
    """Three identical history months (Jul-Sep): salary plus per-category spend."""
    rows: list[ScenarioTransaction] = []
    for year, month in ((2026, 7), (2026, 8), (2026, 9)):
        rows.append(_salary_month(year, month, salary))
        for index, (category, amount) in enumerate(sorted(categories.items())):
            rows.append(_tx(f"{year}-{month:02d}-{9 + index * 5:02d}", amount,
                            category, category_conf(category)))
    return RecommendationScenario(user_key, tuple(rows))


def category_conf(category: str) -> str:
    return {
        "Food": "Dhaka Biryani House",
        "Entertainment": "Star Cineplex",
        "Shopping": "Aarong",
        "Salary": "Acme Corp Payroll",
    }.get(category, category)


def coach_scenario(user_key: str, august_food: str, september_food: str,
                   consumer_categories: dict[str, tuple[str, str]] | None = None) -> RecommendationScenario:
    """Coach-flow world with controllable August/September spending.

    ``consumer_categories`` maps a category to (august_amount, september_amount).
    """
    rows: list[ScenarioTransaction] = [
        _tx("2026-07-05", "30000", "Salary", "Acme Corp Payroll"),
        _tx("2026-07-10", "-4000", "Food", "Dhaka Biryani House"),
        _tx("2026-08-05", "30000", "Salary", "Acme Corp Payroll"),
        _tx("2026-08-12", august_food, "Food", "Dhaka Biryani House"),
        _tx("2026-09-05", "30000", "Salary", "Acme Corp Payroll"),
        _tx("2026-09-12", september_food, "Food", "Dhaka Biryani House"),
    ]
    for index, (category, (august, september)) in enumerate(sorted((consumer_categories or {}).items())):
        rows.append(_tx(f"2026-08-{16 + index:02d}", august, category, category_conf(category)))
        rows.append(_tx(f"2026-09-{16 + index:02d}", september, category, category_conf(category)))
    return RecommendationScenario(user_key, tuple(rows))


CANARY_TRANSACTIONS = (
    ScenarioTransaction(date(2026, 9, 8), "-777777", "Food",
                        RECOMMENDATION_ISOLATION_CANARY_MERCHANT),
)


# -- plan worlds --------------------------------------------------------------

PLAN_AT_RISK_SCENARIO = plan_scenario(
    "plan_at_risk", "20000",
    {"Food": "-12000", "Entertainment": "-1000"})   # surplus 7000 < required 10000

PLAN_ON_TRACK_SCENARIO = plan_scenario(
    "plan_on_track", "30000", {"Food": "-4000"})    # surplus 26000 >= required 10000

PLAN_INSUFFICIENT_SCENARIO = RecommendationScenario("plan_insufficient", ())


# -- coach worlds -------------------------------------------------------------

COACH_INCREASED_SCENARIO = coach_scenario(
    "coach_increased", "-5000", "-9000",
    {"Shopping": ("-2000", "-3000")})               # Food and Shopping both jump >10%

COACH_STABLE_SCENARIO = coach_scenario(
    "coach_stable", "-5000", "-5000")               # no increase at all

COACH_TWO_MONTHS_SCENARIO = RecommendationScenario(
    "coach_two_months",
    (
        _tx("2026-08-05", "30000", "Salary", "Acme Corp Payroll"),
        _tx("2026-08-12", "-5000", "Food", "Dhaka Biryani House"),
        _tx("2026-09-05", "30000", "Salary", "Acme Corp Payroll"),
        _tx("2026-09-12", "-9000", "Food", "Dhaka Biryani House"),
    ),
    history_months=2)                               # July missing: history inadequate

COACH_NON_REDUCIBLE_SCENARIO = coach_scenario(
    "coach_non_reducible", "-5000", "-5000",
    {"Bills": ("-5000", "-9000")})                  # Bills spike but is not treated as optional


# ---------------------------------------------------------------------------
# Case definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanCase:
    case_id: str
    group: str
    scenario: RecommendationScenario
    goal_amount: str
    current_saved: str
    target_date: str
    today: str
    expected_status: str
    expected_fields: tuple[tuple[str, object], ...]   # plan key -> pinned value (None allowed)
    expected_recommendations: tuple[tuple[str, str, str], ...]  # (category, monthly_spending, cut)
    limitation_contains: str | None = None


@dataclass(frozen=True)
class CoachCase:
    case_id: str
    group: str
    scenario: RecommendationScenario
    expected_recommendations: tuple[tuple[str, str, str, str], ...]  # (category, saving, latest, previous)
    limitation_contains: str | None = None


PLAN_GOAL = ("60000", "30000", "2026-12-31", "2026-10-25")  # goal, saved, target, today

PLAN_AT_RISK_CASE = PlanCase(
    case_id="plan_recommendations_at_risk",
    group="plan_recommendations",
    scenario=PLAN_AT_RISK_SCENARIO,
    goal_amount=PLAN_GOAL[0], current_saved=PLAN_GOAL[1],
    target_date=PLAN_GOAL[2], today=PLAN_GOAL[3],
    expected_status="at_risk",
    expected_fields=(
        ("status", "at_risk"),
        ("goal_amount", "60000"),
        ("current_saved", "30000"),
        ("remaining_goal", "30000"),
        ("months_remaining", 3),
        ("required_monthly_saving", "10000"),
        ("estimated_monthly_income", "20000"),
        ("estimated_monthly_spending", "13000"),
        ("estimated_monthly_surplus", "7000"),
        ("recommended_monthly_cut", "2600"),
        ("projected_monthly_saving", "9600"),
        ("historical_transaction_count", 9),
    ),
    expected_recommendations=(
        ("Food", "12000", "2400"),
        ("Entertainment", "1000", "200"),
    ),
)

PLAN_ON_TRACK_CASE = PlanCase(
    case_id="plan_recommendations_on_track",
    group="plan_recommendations",
    scenario=PLAN_ON_TRACK_SCENARIO,
    goal_amount=PLAN_GOAL[0], current_saved=PLAN_GOAL[1],
    target_date=PLAN_GOAL[2], today=PLAN_GOAL[3],
    expected_status="on_track",
    expected_fields=(
        ("status", "on_track"),
        ("remaining_goal", "30000"),
        ("months_remaining", 3),
        ("required_monthly_saving", "10000"),
        ("estimated_monthly_income", "30000"),
        ("estimated_monthly_spending", "4000"),
        ("estimated_monthly_surplus", "26000"),
        ("recommended_monthly_cut", "0"),
        ("projected_monthly_saving", "26000"),
        ("historical_transaction_count", 6),
    ),
    expected_recommendations=(),
)

PLAN_COMPLETE_CASE = PlanCase(
    case_id="plan_recommendations_goal_met",
    group="plan_recommendations",
    scenario=PLAN_ON_TRACK_SCENARIO,
    goal_amount=PLAN_GOAL[0], current_saved="60000",
    target_date=PLAN_GOAL[2], today=PLAN_GOAL[3],
    expected_status="complete",
    expected_fields=(
        ("status", "complete"),
        ("remaining_goal", "0"),
        ("required_monthly_saving", "0"),
        ("recommended_monthly_cut", "0"),
    ),
    expected_recommendations=(),
)

PLAN_INSUFFICIENT_CASE = PlanCase(
    case_id="plan_recommendations_insufficient_data",
    group="plan_recommendations",
    scenario=PLAN_INSUFFICIENT_SCENARIO,
    goal_amount=PLAN_GOAL[0], current_saved=PLAN_GOAL[1],
    target_date=PLAN_GOAL[2], today=PLAN_GOAL[3],
    expected_status="insufficient_data",
    expected_fields=(
        ("status", "insufficient_data"),
        ("required_monthly_saving", "10000"),
        ("estimated_monthly_income", None),
        ("estimated_monthly_spending", None),
        ("estimated_monthly_surplus", None),
        ("projected_monthly_saving", None),
        ("recommended_monthly_cut", "0"),
        ("historical_transaction_count", 0),
    ),
    expected_recommendations=(),
    limitation_contains="No usable actual history is recorded",
)

PLAN_CASES: tuple[PlanCase, ...] = (
    PLAN_AT_RISK_CASE, PLAN_ON_TRACK_CASE, PLAN_COMPLETE_CASE, PLAN_INSUFFICIENT_CASE)


COACH_INCREASED_CASE = CoachCase(
    case_id="coach_recommendations_category_increases",
    group="coach_recommendations",
    scenario=COACH_INCREASED_SCENARIO,
    expected_recommendations=(
        ("Food", "900", "9000", "5000"),
        ("Shopping", "300", "3000", "2000"),
    ),
)

COACH_STABLE_CASE = CoachCase(
    case_id="coach_recommendations_no_increase",
    group="coach_recommendations",
    scenario=COACH_STABLE_SCENARIO,
    expected_recommendations=(),
)

COACH_TWO_MONTHS_CASE = CoachCase(
    case_id="coach_recommendations_insufficient_history",
    group="coach_recommendations",
    scenario=COACH_TWO_MONTHS_SCENARIO,
    expected_recommendations=(),
    limitation_contains="Three complete calendar months",
)

COACH_NON_REDUCIBLE_CASE = CoachCase(
    case_id="coach_recommendations_non_reducible_spike",
    group="coach_recommendations",
    scenario=COACH_NON_REDUCIBLE_SCENARIO,
    expected_recommendations=(),
)

COACH_CASES: tuple[CoachCase, ...] = (
    COACH_INCREASED_CASE, COACH_STABLE_CASE,
    COACH_TWO_MONTHS_CASE, COACH_NON_REDUCIBLE_CASE)


# ---------------------------------------------------------------------------
# Spec-derived ground truth (plain arithmetic; never calls the services)
# ---------------------------------------------------------------------------


def expected_plan(scenario: RecommendationScenario, goal_amount: str, current_saved: str,
                  target_date: str, today: str) -> dict:
    """Recompute the whole savings-plan contract from the blueprint."""
    goal, saved = Decimal(goal_amount), Decimal(current_saved)
    target, as_of_today = date.fromisoformat(target_date), date.fromisoformat(today)

    usable = [tx for tx in scenario.transactions
              if tx.date <= as_of_today and Decimal(tx.amount) != 0]

    remaining = max(Decimal("0"), goal - saved)
    months = max(1, (target.year - as_of_today.year) * 12
                 + (target.month - as_of_today.month) + 1)
    required = remaining / months

    income_by: dict[str, Decimal] = {}
    expenses_by: dict[str, Decimal] = {}
    category_by_month: dict[str, dict[str, Decimal]] = {}
    for tx in usable:
        key = f"{tx.date.year:04d}-{tx.date.month:02d}"
        amount = Decimal(tx.amount)
        if amount > 0:
            income_by[key] = income_by.get(key, Decimal("0")) + amount
        elif amount < 0:
            expenses_by[key] = expenses_by.get(key, Decimal("0")) - amount
            months_by_category = category_by_month.setdefault(key, {})
            months_by_category[tx.category] = (
                months_by_category.get(tx.category, Decimal("0")) - amount)

    month_keys = sorted(set(income_by) | set(expenses_by))
    if month_keys:
        estimated_income = sum(income_by.get(k, Decimal("0")) for k in month_keys) / len(month_keys)
        estimated_spending = sum(expenses_by.get(k, Decimal("0")) for k in month_keys) / len(month_keys)
    else:
        estimated_income = Decimal("0")
        estimated_spending = Decimal("0")
    estimated_surplus = estimated_income - estimated_spending
    shortfall = max(Decimal("0"), required - estimated_surplus)

    if required == 0:
        observed_status = "complete"
    elif not usable:
        observed_status = "insufficient_data"
    elif estimated_surplus >= required:
        observed_status = "on_track"
    else:
        observed_status = "at_risk"

    recommendations = []
    remaining_shortfall = shortfall
    if remaining_shortfall > 0 and month_keys:
        categories = []
        for category in {c for month in category_by_month.values() for c in month}:
            average = sum(
                month_by.get(category, Decimal("0"))
                for month_by in category_by_month.values()) / len(month_keys)
            categories.append((category, average))
        categories.sort(key=lambda item: (-item[1], item[0]))
        for category, average in categories:
            if average <= 0:
                continue
            cut = min(average * PLAN_REDUCTION_FRACTION, remaining_shortfall)
            if cut <= 0:
                continue
            recommendations.append((category, average, cut))
            remaining_shortfall -= cut
            if remaining_shortfall <= 0:
                break

    result = {
        "status": observed_status,
        "goal_amount": _plan_round(goal),
        "current_saved": _plan_round(saved),
        "remaining_goal": _plan_round(remaining),
        "months_remaining": months,
        "required_monthly_saving": _plan_round(required),
        "estimated_monthly_income": _plan_round(estimated_income),
        "estimated_monthly_spending": _plan_round(estimated_spending),
        "estimated_monthly_surplus": _plan_round(estimated_surplus),
        "recommended_monthly_cut": _plan_round(sum((c for _, _, c in recommendations), Decimal("0"))),
        "projected_monthly_saving": _plan_round(estimated_surplus
                                               + sum((c for _, _, c in recommendations), Decimal("0"))),
        "historical_transaction_count": len(usable),
        "recommendations": [
            (category, _plan_round(spending), _plan_round(cut))
            for category, spending, cut in recommendations
        ],
    }
    if not usable:
        for field in ("estimated_monthly_income", "estimated_monthly_spending",
                      "estimated_monthly_surplus", "projected_monthly_saving"):
            result[field] = None
    return result


def category_monthly_averages(scenario: RecommendationScenario) -> dict[str, Decimal]:
    """Per-category monthly averages over every month with any activity."""
    income_months: set[str] = set()
    category_by_month: dict[str, dict[str, Decimal]] = {}
    for tx in scenario.transactions:
        if Decimal(tx.amount) >= 0:
            income_months.add(f"{tx.date.year:04d}-{tx.date.month:02d}")
            continue
        key = f"{tx.date.year:04d}-{tx.date.month:02d}"
        months_by_category = category_by_month.setdefault(key, {})
        months_by_category[tx.category] = (
            months_by_category.get(tx.category, Decimal("0")) - Decimal(tx.amount))
    month_keys = sorted(set(income_months) | set(category_by_month))
    averages: dict[str, Decimal] = {}
    for category in {c for month in category_by_month.values() for c in month}:
        averages[category] = sum(
            month_by.get(category, Decimal("0")) for month_by in category_by_month.values()
        ) / len(month_keys)
    return averages


def monthly_expenses(scenario: RecommendationScenario, year: int, month: int,
                     category: str | None = None) -> Decimal:
    return money(sum(
        (-Decimal(tx.amount) if (Decimal(tx.amount) < 0 and tx.date.year == year
                                 and tx.date.month == month
                                 and (category is None or tx.category == category))
         else Decimal("0"))
        for tx in scenario.transactions))


def expected_coach_recommendations(scenario: RecommendationScenario,
                                   as_of=date(2026, 10, 25)) -> list[tuple[str, Decimal, Decimal, Decimal]]:
    """(category, latest, previous, estimate) per increased reducible category.

    The coach contract: latest = the calendar month before as_of, previous =
    the month before that; a category must be in the reducible set, its
    latest spending must exceed 110% of the previous month, and the estimate
    is at most 10% of the latest figure.
    """
def expected_coach_recommendations(scenario: RecommendationScenario,
                                   as_of=date(2026, 10, 25)) -> list[tuple[str, Decimal, Decimal, Decimal]]:
    """(category, latest, previous, estimate) per increased reducible category.

    The coach contract: latest = the calendar month before as_of, previous =
    the month before that; the three history months must each hold records,
    a category must be in the reducible set, its latest spending must exceed
    110% of the previous month, and the estimate is at most 10% of the
    latest figure.
    """
    history_start, history_end = _shift(as_of, -3), _day_before(_shift(as_of, 0))
    observed = set()
    for tx in scenario.transactions:
        if history_start <= tx.date <= history_end:
            observed.add(f"{tx.date.year:04d}-{tx.date.month:02d}")
    expected_span = ((history_end.year * 12 + history_end.month)
                     - (history_start.year * 12 + history_start.month) + 1)
    if len(observed) < expected_span:
        return []  # inadequate history: the coach must make no recommendation
    latest_start, previous_start = _shift(as_of, -1), _shift(as_of, -2)
    windows = (
        (latest_start, _day_before(_shift(latest_start, 1))),
        (previous_start, _day_before(_shift(previous_start, 1))),
    )
    latest, previous = {}, {}
    for tx in scenario.transactions:
        if Decimal(tx.amount) >= 0:
            continue
        for index, (start, end) in enumerate(windows):
            if start <= tx.date <= end:
                latest_or_previous = (latest, previous)[index]
                latest_or_previous[tx.category] = (
                    latest_or_previous.get(tx.category, Decimal("0")) - Decimal(tx.amount))
    derived = []
    for category in sorted(latest):
        if category not in REDUCIBLE_CATEGORIES:
            continue
        current, prior = latest[category], previous.get(category, Decimal("0"))
        if prior <= 0 or current <= prior * COACH_INCREASE_FACTOR:
            continue
        saving = money(min(current * COACH_REDUCTION_FRACTION, current - prior))
        if saving <= 0:
            continue
        derived.append((category, current, prior, saving))
    derived.sort(key=lambda item: (-item[3], item[0]))
    return derived


def _shift(value: date, offset: int) -> date:
    """First day of the month ``offset`` calendar months from ``value``."""
    index = value.year * 12 + value.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def _day_before(value: date) -> date:
    from datetime import timedelta
    return value - timedelta(days=1)


def recommendation_ground_truth_consistency(
    plan_cases: tuple[PlanCase, ...] = PLAN_CASES,
    coach_cases: tuple[CoachCase, ...] = COACH_CASES,
) -> list[str]:
    """Re-derive every pinned number from the blueprint with plain arithmetic."""
    problems: list[str] = []
    for case in plan_cases:
        where = f"{case.case_id}"
        truth = expected_plan(case.scenario, case.goal_amount, case.current_saved,
                              case.target_date, case.today)
        if truth["status"] != case.expected_status:
            problems.append(f"{where}: expected status {case.expected_status!r} "
                            f"conflicts with spec status {truth['status']!r}")
        for key, expected in case.expected_fields:
            actual = truth.get(key, "<missing>")
            if not _field_matches(actual, expected):
                problems.append(f"{where}: field '{key}' pinned as {expected!r} "
                                f"but spec derives {actual!r}")
        pinned = [(category, Decimal(spending), Decimal(cut))
                  for category, spending, cut in case.expected_recommendations]
        if pinned != truth["recommendations"]:
            problems.append(f"{where}: pinned recommendations {pinned} "
                            f"conflict with spec recommendations {truth['recommendations']}")

    for case in coach_cases:
        where = f"{case.case_id}"
        truth = expected_coach_recommendations(case.scenario, RECOMMENDATION_AS_OF)
        pinned = [(category, Decimal(saving), Decimal(latest), Decimal(previous))
                  for category, saving, latest, previous in case.expected_recommendations]
        derived = [(category, saving, latest, previous)
                   for category, latest, previous, saving in truth]
        if pinned != derived:
            problems.append(f"{where}: pinned recommendations {pinned} "
                            f"conflict with spec recommendations {derived}")
        if case.limitation_contains and truth:
            problems.append(f"{where}: a limitation of {case.limitation_contains!r} is pinned "
                            f"but the spec expects recommendations {truth}")
        inadequate = case.scenario.history_months < 3
        if inadequate and truth:
            problems.append(f"{where}: history is inadequate (2 months) "
                            f"but the spec derives recommendations {truth}")
    return problems


def _field_matches(actual, expected) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual == expected
    if expected is None or actual is None:
        return actual is expected or (actual is None and expected is None)
    if isinstance(expected, int) and not isinstance(expected, bool):
        try:
            return int(actual) == expected
        except (TypeError, ValueError):
            return False
    actual_decimal = _decimal(actual)
    expected_decimal = _decimal(expected)
    if actual_decimal is not None and expected_decimal is not None:
        return actual_decimal == expected_decimal
    return str(actual) == str(expected)


def _decimal(value):
    try:
        return Decimal(str(value))
    except Exception:
        return None


CANARY_SCENARIO = RecommendationScenario("rec_isolation_canary", CANARY_TRANSACTIONS)


def seed_recommendation_scenarios(db, scenarios: tuple[RecommendationScenario, ...]) -> list:
    """Seed the given worlds as fresh users; returns the created users."""
    from uuid import uuid4
    from app.models import User, Transaction

    emails = [f"rec-{uuid4().hex}@example.com" for _ in scenarios]
    for email in emails:
        db.add(User(email=email, hashed_password="evaluation"))
    db.commit()
    users = [db.query(User).filter(User.email == email).one() for email in emails]
    for user, scenario in zip(users, scenarios):
        for tx in scenario.transactions:
            db.add(Transaction(user_id=user.id, date=tx.date, amount=Decimal(tx.amount),
                               category=tx.category, merchant=tx.merchant))
    db.commit()
    return users


def clear_recommendation_scenarios(db, users) -> None:
    from app.models import User
    from app.models.transactions import Transaction

    for user in users:
        db.query(Transaction).filter_by(user_id=user.id).delete()
        db.query(User).filter(User.id == user.id).delete()
    db.commit()


def validate_recommendation_dataset() -> list[str]:
    problems = list(recommendation_ground_truth_consistency())
    ids = [case.case_id for case in PLAN_CASES + COACH_CASES]
    if len(ids) != len(set(ids)):
        problems.append("recommendation case ids are not unique")
    if not any(case.expected_status == "insufficient_data" for case in PLAN_CASES):
        problems.append("recommendation dataset lacks an insufficient-data plan case")
    return problems
