"""Controlled scenarios for the AI-12D proactive-insight evaluation.

Each scenario is a "world" whose every financial number is pinned in the
blueprint below.  For every insight type the dataset contains at least one
*triggered* world (condition true -> insight must exist) and one *silent*
world (condition false -> insight must be absent).  Ground truth numbers and
dates are written as literals on the expected insights and are re-derived
with plain arithmetic by :func:`insight_ground_truth_consistency`, so a pin
that disagrees with the scenario spec fails the dataset check before any
system-under-test is involved.

Proactive insights are judged on structured financial claims (type, numbers,
dates) — never on natural-language wording.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from app.evaluation.datasets.finance_scenario import (
    AS_OF,
    ScheduledEntry,
    ScenarioTransaction,
)

INSIGHT_AS_OF = AS_OF  # 2026-10-25; every window below derives from this

# Contract constants the insights derive from (product definition, so the
# ground-truth helpers may copy them independently).
COACH_REDUCTION_FRACTION = Decimal("0.10")   # suggested cut = up to 10% of latest spending
COACH_INCREASE_FACTOR = Decimal("1.10")      # fires when spending > 110% of the prior month
UNUSUAL_FACTOR = Decimal("1.5")              # fires when current month > 150% of the prior ceiling
UPCOMING_HORIZON_DAYS = 30

REDUCIBLE_CATEGORIES = frozenset(
    {"Food", "Shopping", "Entertainment", "Subscription", "Travel"})

UPCOMING_EXPENSE = "upcoming_expense"
SAVINGS_OPPORTUNITY = "savings_opportunity"
UNUSUAL_SPENDING = "unusual_spending"
PROJECTED_SHORTFALL = "projected_shortfall"
GOAL_PROGRESS = "goal_progress"

KNOWN_INSIGHT_TYPES = frozenset({
    UPCOMING_EXPENSE, SAVINGS_OPPORTUNITY, UNUSUAL_SPENDING,
    PROJECTED_SHORTFALL, GOAL_PROGRESS,
})

# Strings that exist only on the isolation canary user; if any of them (or
# the canary amounts) appears inside a main-user insight payload, user
# isolation has been broken.
INSIGHT_ISOLATION_CANARY_TRANSACTION = "CANARY PRIVATE LEDGER"
INSIGHT_ISOLATION_CANARY_BILL = "CANARY PRIVATE BILL"
INSIGHT_ISOLATION_CANARY_GOAL = "CANARY PRIVATE GOAL"
INSIGHT_ISOLATION_MARKERS = (
    INSIGHT_ISOLATION_CANARY_TRANSACTION,
    INSIGHT_ISOLATION_CANARY_BILL,
    INSIGHT_ISOLATION_CANARY_GOAL,
    "777777",
    "888888",
)


def money(value: Decimal) -> Decimal:
    """Money rounding copied from the coach contract (half-up, 2 dp)."""
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def month_shift(value: date, offset: int) -> date:
    """First day of the month ``offset`` calendar months from ``value``."""
    index = value.year * 12 + value.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def month_end(first_day: date) -> date:
    return month_shift(first_day, 1) - timedelta(days=1)


def history_window(as_of: date) -> tuple[date, date]:
    """Three complete calendar months before the as_of month (coach contract)."""
    return month_shift(as_of, -3), month_shift(as_of, 0) - timedelta(days=1)


def latest_month_window(as_of: date) -> tuple[date, date]:
    """The month used for "latest" spending in recommendation evidence."""
    first = month_shift(as_of, -1)
    return first, month_end(first)


def previous_month_window(as_of: date) -> tuple[date, date]:
    return month_shift(as_of, -2), month_end(month_shift(as_of, -2))


def current_month_window(as_of: date) -> tuple[date, date]:
    return date(as_of.year, as_of.month, 1), as_of


def expire_date(as_of: date) -> date:
    return month_shift(as_of, 1)


@dataclass(frozen=True)
class GoalEntry:
    """A savings goal row as pinned in the scenario blueprint."""

    name: str
    target_amount: str
    current_saved: str
    target_date: str
    status: str = "active"


@dataclass(frozen=True)
class InsightScenario:
    """One peer user's whole financial world for an insight case."""

    user_key: str
    transactions: tuple[ScenarioTransaction, ...]
    scheduled: tuple[ScheduledEntry, ...] = ()
    goals: tuple[GoalEntry, ...] = ()


@dataclass(frozen=True)
class ExpectedInsight:
    """Structured expectation for one insight type in one case.

    Numbers are pinned as literals and re-derived by
    :func:`insight_ground_truth_consistency`; wording is deliberately not
    pinned.  ``evidence_sets`` holds one (path, expected) tuple per expected
    instance (order-independent matching); ``"!non_null"`` requires presence.
    """

    type: str
    count: int = 0
    evidence_sets: tuple[tuple[tuple[str, str], ...], ...] = ()
    period: tuple[str, str] | None = None          # (period_start, period_end) iso
    expires_on: str | None = None
    category: str | None = None                    # savings_opportunity category
    title_contains: str | None = None
    plan_marked: bool = False                      # scheduled != actual marking


@dataclass(frozen=True)
class InsightCase:
    case_id: str
    behavior: str                                  # "triggered" | "silent"
    scenario: InsightScenario
    expected: tuple[ExpectedInsight, ...]


# ---------------------------------------------------------------------------
# Scenario builders
#
# History layout understood by the coach inside the nudges flow:
#   history months   : July, August, September 2026 (July 1 .. Sep 30)
#   latest month     : September  (recommendation evidence: "latest")
#   previous month   : August     (recommendation evidence: "previous")
#   current window   : October 1 .. as_of   (unusual-spending evidence)
# ---------------------------------------------------------------------------


def _tx(iso: str, amount: str, category: str, merchant: str) -> ScenarioTransaction:
    return ScenarioTransaction(date.fromisoformat(iso), amount, category, merchant)


def _history_salary(year: int, month: int, amount: str = "30000") -> ScenarioTransaction:
    return _tx(f"{year}-{month:02d}-05", amount, "Salary", "Acme Corp Payroll")


# -- unusual spending ---------------------------------------------------------


def _unusual_base(october_food: str) -> InsightScenario:
    """Three flat months of ৳4,000 Food spending, then a current-month figure."""
    return InsightScenario(
        user_key="unusual",
        transactions=(
            _history_salary(2026, 7), _tx("2026-07-10", "-4000", "Food", "Dhaka Biryani House"),
            _history_salary(2026, 8), _tx("2026-08-10", "-4000", "Food", "Dhaka Biryani House"),
            _history_salary(2026, 9), _tx("2026-09-10", "-4000", "Food", "Dhaka Biryani House"),
            _history_salary(2026, 10), _tx("2026-10-06", october_food, "Food", "Dhaka Biryani House"),
        ),
    )


UNUSUAL_TRUE_SCENARIO = _unusual_base("-9000")    # 9000 > 1.5 x 4000
UNUSUAL_FALSE_SCENARIO = _unusual_base("-4000")   # 4000 <= 1.5 x 4000


# -- savings opportunity (category increase) -----------------------------------


def _savings_base(september_food: str) -> InsightScenario:
    """August and September Food spending control the increase condition."""
    return InsightScenario(
        user_key="savings",
        transactions=(
            _history_salary(2026, 7), _tx("2026-07-10", "-4000", "Food", "Dhaka Biryani House"),
            _history_salary(2026, 8), _tx("2026-08-12", "-5000", "Food", "Dhaka Biryani House"),
            _history_salary(2026, 9), _tx("2026-09-12", september_food, "Food", "Dhaka Biryani House"),
        ),
    )


SAVINGS_TRUE_SCENARIO = _savings_base("-9000")    # 9000 > 1.1 x 5000
SAVINGS_FALSE_SCENARIO = _savings_base("-5000")   # 5000 <= 1.1 x 5000


# -- upcoming scheduled obligation ---------------------------------------------


def _bill_history() -> tuple[ScenarioTransaction, ...]:
    return (
        _history_salary(2026, 7), _tx("2026-07-10", "-2000", "Food", "Dhaka Biryani House"),
        _history_salary(2026, 8), _tx("2026-08-10", "-2000", "Food", "Dhaka Biryani House"),
        _history_salary(2026, 9), _tx("2026-09-10", "-2000", "Food", "Dhaka Biryani House"),
        _history_salary(2026, 10), _tx("2026-10-10", "-2000", "Food", "Dhaka Biryani House"),
    )


UPCOMING_TRUE_SCENARIO = InsightScenario(
    user_key="upcoming_true",
    transactions=_bill_history(),
    scheduled=(
        ScheduledEntry("Electricity bill", "expense", "6000.00", "scheduled", AS_OF + timedelta(days=3)),
        # Paid plans are facts, not obligations: must never be surfaced as upcoming.
        ScheduledEntry("Old rent", "expense", "9000.00", "paid", AS_OF + timedelta(days=1)),
    ),
)

UPCOMING_FALSE_SCENARIO = InsightScenario(
    user_key="upcoming_false",
    transactions=_bill_history(),
    scheduled=(
        ScheduledEntry("Future rent", "expense", "9000.00", "scheduled", AS_OF + timedelta(days=40)),
        ScheduledEntry("Settled bill", "expense", "500.00", "paid", AS_OF + timedelta(days=2)),
        ScheduledEntry("Bonus expectation", "income", "20000.00", "scheduled", AS_OF + timedelta(days=5)),
    ),
)


# -- projected shortfall --------------------------------------------------------


def _shortfall_base(monthly_bills: str) -> InsightScenario:
    """Salary 20000 and Bills spending control the monthly net sign."""
    return InsightScenario(
        user_key="shortfall",
        transactions=(
            _history_salary(2026, 7, "20000"), _tx("2026-07-10", monthly_bills, "Bills", "DESCO Electricity"),
            _history_salary(2026, 8, "20000"), _tx("2026-08-10", monthly_bills, "Bills", "DESCO Electricity"),
            _history_salary(2026, 9, "20000"), _tx("2026-09-10", monthly_bills, "Bills", "DESCO Electricity"),
            _history_salary(2026, 10, "20000"), _tx("2026-10-06", monthly_bills, "Bills", "DESCO Electricity"),
        ),
    )


SHORTFALL_TRUE_SCENARIO = _shortfall_base("-25000")   # 20000 - 25000 < 0
SHORTFALL_FALSE_SCENARIO = _shortfall_base("-15000")  # 20000 - 15000 > 0


# -- goal progress ---------------------------------------------------------------


def _goal_base() -> InsightScenario:
    """Comfortable surplus (40000 income / 5000 food) with one active goal."""
    return InsightScenario(
        user_key="goal",
        transactions=(
            _history_salary(2026, 7, "40000"), _tx("2026-07-10", "-5000", "Food", "Dhaka Biryani House"),
            _history_salary(2026, 8, "40000"), _tx("2026-08-10", "-5000", "Food", "Dhaka Biryani House"),
            _history_salary(2026, 9, "40000"), _tx("2026-09-10", "-5000", "Food", "Dhaka Biryani House"),
            _history_salary(2026, 10, "40000"), _tx("2026-10-06", "-5000", "Food", "Dhaka Biryani House"),
        ),
    )


GOAL_TRUE_SCENARIO = InsightScenario(
    user_key="goal_true",
    transactions=_goal_base().transactions,
    goals=(GoalEntry("Emergency fund", "60000", "30000", "2026-12-31"),),
)

GOAL_FALSE_SCENARIO = InsightScenario(
    user_key="goal_false",
    transactions=_goal_base().transactions,
)


# -- insufficient history (insights must not fire) --------------------------------

INSUFFICIENT_HISTORY_SCENARIO = InsightScenario(
    user_key="insufficient",
    # July is empty: history is inadequate even though October spikes.
    transactions=(
        _history_salary(2026, 8), _tx("2026-08-10", "-4000", "Food", "Dhaka Biryani House"),
        _history_salary(2026, 9), _tx("2026-09-10", "-9000", "Food", "Dhaka Biryani House"),
        _history_salary(2026, 10), _tx("2026-10-06", "-9000", "Food", "Dhaka Biryani House"),
    ),
)


# -- isolation canary --------------------------------------------------------------

CANARY_SCENARIO = InsightScenario(
    user_key="isolation_canary",
    transactions=(
        ScenarioTransaction(date(2026, 9, 8), "-777777", "Food",
                            INSIGHT_ISOLATION_CANARY_TRANSACTION),
    ),
    scheduled=(
        ScheduledEntry(INSIGHT_ISOLATION_CANARY_BILL, "expense", "888888.00", "scheduled",
                       AS_OF + timedelta(days=2)),
    ),
    goals=(GoalEntry(INSIGHT_ISOLATION_CANARY_GOAL, "100000", "50000", "2026-12-31"),),
)


# ---------------------------------------------------------------------------
# Expected insights (numbers pinned as literals; consistency-checked below)
# ---------------------------------------------------------------------------


def _savings_expected(*sets: tuple[tuple[str, str], ...], category: str) -> ExpectedInsight:
    return ExpectedInsight(
        type=SAVINGS_OPPORTUNITY, count=1, evidence_sets=(sets,), category=category,
        title_contains=category,
        period=(latest_month_window(INSIGHT_AS_OF)[0].isoformat(),
                latest_month_window(INSIGHT_AS_OF)[1].isoformat()),
        expires_on=expire_date(INSIGHT_AS_OF).isoformat(),
    )


NO_INSIGHTS = (
    ExpectedInsight(type=UPCOMING_EXPENSE),
    ExpectedInsight(type=SAVINGS_OPPORTUNITY),
    ExpectedInsight(type=UNUSUAL_SPENDING),
    ExpectedInsight(type=PROJECTED_SHORTFALL),
    ExpectedInsight(type=GOAL_PROGRESS),
)

UNUSUAL_TRIGGERED = (
    ExpectedInsight(
        type=UNUSUAL_SPENDING, count=1,
        evidence_sets=((("current_expenses", "9000.00"), ("largest_prior_month", "4000.00")),),
        period=("2026-10-01", "2026-10-25"),
        expires_on="2026-11-01",
        title_contains="spending",
    ),
    ExpectedInsight(type=SAVINGS_OPPORTUNITY),  # September = August: no increase
    ExpectedInsight(type=UPCOMING_EXPENSE),
    ExpectedInsight(type=PROJECTED_SHORTFALL),
    ExpectedInsight(type=GOAL_PROGRESS),
)

SAVINGS_TRIGGERED = (
    ExpectedInsight(
        type=SAVINGS_OPPORTUNITY, count=1, category="Food", title_contains="Food",
        evidence_sets=((("latest_expenses", "9000.00"), ("previous_expenses", "5000.00"),
                        ("estimated_monthly_saving", "900.00")),),
        period=("2026-09-01", "2026-09-30"),
        expires_on="2026-11-01",
    ),
    ExpectedInsight(type=UNUSUAL_SPENDING),      # no October transactions at all
    ExpectedInsight(type=UPCOMING_EXPENSE),
    ExpectedInsight(type=PROJECTED_SHORTFALL),
    ExpectedInsight(type=GOAL_PROGRESS),
)

UPCOMING_TRIGGERED = (
    ExpectedInsight(
        type=UPCOMING_EXPENSE, count=1, plan_marked=True,
        evidence_sets=((("amount", "6000.00"), ("title", "Electricity bill"),
                        ("record_type", "plan"), ("scheduled_item_id", "!non_null")),),
        period=("2026-10-25", "2026-10-28"),
        expires_on="2026-10-29",
    ),
    ExpectedInsight(type=SAVINGS_OPPORTUNITY),
    ExpectedInsight(type=UNUSUAL_SPENDING),
    ExpectedInsight(type=PROJECTED_SHORTFALL),
    ExpectedInsight(type=GOAL_PROGRESS),
)

SHORTFALL_TRIGGERED = (
    ExpectedInsight(
        type=PROJECTED_SHORTFALL, count=1,
        evidence_sets=((("estimated_monthly_net", "-5000.00"), ("is_estimate", "True")),),
        period=("2026-10-25", "2026-10-31"),
        expires_on="2026-11-01",
        title_contains="deficit",
    ),
    ExpectedInsight(type=SAVINGS_OPPORTUNITY),
    ExpectedInsight(type=UNUSUAL_SPENDING),
    ExpectedInsight(type=UPCOMING_EXPENSE),
    ExpectedInsight(type=GOAL_PROGRESS),
)

GOAL_TRIGGERED = (
    ExpectedInsight(
        type=GOAL_PROGRESS, count=1,
        evidence_sets=((("goal_id", "!non_null"), ("name", "Emergency fund"),
                        ("current_saved", "30000.00"), ("affordability", "appears_feasible"),
                        ("saved_source", "user_reported")),),
        period=("2026-10-25", "2026-12-31"),
        expires_on="2026-11-01",
    ),
    ExpectedInsight(type=SAVINGS_OPPORTUNITY),
    ExpectedInsight(type=UNUSUAL_SPENDING),
    ExpectedInsight(type=UPCOMING_EXPENSE),
    ExpectedInsight(type=PROJECTED_SHORTFALL),
)


INSIGHT_EVALUATION_CASES: tuple[InsightCase, ...] = (
    InsightCase("insight_unusual_spending_triggered", "triggered",
                UNUSUAL_TRUE_SCENARIO, UNUSUAL_TRIGGERED),
    InsightCase("insight_unusual_spending_silent", "silent",
                UNUSUAL_FALSE_SCENARIO, NO_INSIGHTS),
    InsightCase("insight_savings_opportunity_triggered", "triggered",
                SAVINGS_TRUE_SCENARIO, SAVINGS_TRIGGERED),
    InsightCase("insight_savings_opportunity_silent", "silent",
                SAVINGS_FALSE_SCENARIO, NO_INSIGHTS),
    InsightCase("insight_upcoming_scheduled_triggered", "triggered",
                UPCOMING_TRUE_SCENARIO, UPCOMING_TRIGGERED),
    InsightCase("insight_upcoming_scheduled_silent", "silent",
                UPCOMING_FALSE_SCENARIO, NO_INSIGHTS),
    InsightCase("insight_projected_shortfall_triggered", "triggered",
                SHORTFALL_TRUE_SCENARIO, SHORTFALL_TRIGGERED),
    InsightCase("insight_projected_shortfall_silent", "silent",
                SHORTFALL_FALSE_SCENARIO, NO_INSIGHTS),
    InsightCase("insight_goal_progress_triggered", "triggered",
                GOAL_TRUE_SCENARIO, GOAL_TRIGGERED),
    InsightCase("insight_goal_progress_silent", "silent",
                GOAL_FALSE_SCENARIO, NO_INSIGHTS),
    InsightCase("insight_insufficient_history_silent", "silent",
                INSUFFICIENT_HISTORY_SCENARIO, NO_INSIGHTS),
)


# ---------------------------------------------------------------------------
# Spec-derived ground truth (plain arithmetic; never calls the coach)
# ---------------------------------------------------------------------------


def _window_expenses(scenario: InsightScenario, start: date, end: date) -> Decimal:
    total = Decimal("0")
    for tx in scenario.transactions:
        if start <= tx.date <= end and Decimal(tx.amount) < 0:
            total += -Decimal(tx.amount)
    return total


def window_expenses(scenario: InsightScenario, start: date, end: date) -> Decimal:
    return _window_expenses(scenario, start, end)


def window_income(scenario: InsightScenario, start: date, end: date) -> Decimal:
    total = Decimal("0")
    for tx in scenario.transactions:
        if start <= tx.date <= end and Decimal(tx.amount) > 0:
            total += Decimal(tx.amount)
    return total


def monthly_expenses_between(scenario: InsightScenario, start: date, end: date) -> list[Decimal]:
    """Total monthly expenses for every calendar month inside [start, end]."""
    totals: dict[str, Decimal] = {}
    for tx in scenario.transactions:
        if not (start <= tx.date <= end) or Decimal(tx.amount) >= 0:
            continue
        key = f"{tx.date.year:04d}-{tx.date.month:02d}"
        totals[key] = totals.get(key, Decimal("0")) - Decimal(tx.amount)
    return [totals[key] for key in sorted(totals)]


def expected_baseline_net(scenario: InsightScenario, as_of: date = INSIGHT_AS_OF) -> Decimal:
    """Average monthly net over the complete history months (forecast contract)."""
    months = monthly_expenses_between(scenario, *history_window(as_of))
    count = max(1, len(months))
    average_income = money(window_income(scenario, *history_window(as_of)) / Decimal(count))
    average_expenses = money(sum(months, Decimal("0")) / Decimal(count))
    return money(average_income - average_expenses)


def expected_coach_recommendations(
    scenario: InsightScenario, as_of: date = INSIGHT_AS_OF,
) -> list[tuple[str, Decimal, Decimal, Decimal]]:
    """(category, latest, previous, estimated saving) per increased category.

    Copies the recommendation contract purely from the blueprint: a category
    is considered only when the three history months each have records, the
    category appears in the reducible set, the latest month spending exceeds
    110% of the previous month, and the estimate is at most 10% of the latest
    figure.
    """
    as_of = as_of or INSIGHT_AS_OF
    history_start, history_end = history_window(as_of)
    observed: set[str] = set()
    for tx in scenario.transactions:
        if history_start <= tx.date <= history_end:
            observed.add(f"{tx.date.year:04d}-{tx.date.month:02d}")
    if len(observed) < (history_end.year * 12 + history_end.month) - (history_start.year * 12 + history_start.month) + 1:
        return []  # inadequate history: the coach must make no recommendation
    latest_start, latest_end = latest_month_window(as_of)
    previous_start, previous_end = previous_month_window(as_of)
    latest: dict[str, Decimal] = {}
    previous: dict[str, Decimal] = {}
    for tx in scenario.transactions:
        if Decimal(tx.amount) >= 0:
            continue
        if latest_start <= tx.date <= latest_end:
            latest[tx.category] = latest.get(tx.category, Decimal("0")) - Decimal(tx.amount)
        if previous_start <= tx.date <= previous_end:
            previous[tx.category] = previous.get(tx.category, Decimal("0")) - Decimal(tx.amount)
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


def insight_ground_truth_consistency(
    cases: tuple[InsightCase, ...] = INSIGHT_EVALUATION_CASES,
) -> list[str]:
    """Re-derive every pinned number/date from the blueprint with plain math."""
    as_of = INSIGHT_AS_OF
    problems: list[str] = []
    for case in cases:
        scenario = case.scenario
        history_start, history_end = history_window(as_of)
        current_start, current_end = current_month_window(as_of)
        history_months = monthly_expenses_between(scenario, history_start, history_end)
        ceiling = max(history_months, default=Decimal("0"))
        current_expenses = _window_expenses(scenario, current_start, current_end)
        derived_recommendations = expected_coach_recommendations(scenario, as_of)

        for spec in case.expected:
            if spec.type not in KNOWN_INSIGHT_TYPES:
                problems.append(f"{case.case_id}: unknown insight type {spec.type!r}")
                continue
            where = f"{case.case_id}/{spec.type}"

            if spec.type == UNUSUAL_SPENDING:
                truth = current_expenses > ceiling * UNUSUAL_FACTOR
                if spec.count != (1 if truth else 0):
                    problems.append(f"{where}: expected count {spec.count} conflicts with "
                                    f"spec condition ({current_expenses} vs ceiling {ceiling})")
                if spec.count:
                    for path, expected in spec.evidence_sets[0]:
                        if path == "current_expenses" and _decimal(expected) != current_expenses:
                            problems.append(f"{where}: current_expenses {expected} != spec {current_expenses}")
                        if path == "largest_prior_month" and _decimal(expected) != ceiling:
                            problems.append(f"{where}: largest_prior_month {expected} != spec {ceiling}")
                    if spec.period != (current_start.isoformat(), current_end.isoformat()):
                        problems.append(f"{where}: period {spec.period} != current window")
                    if spec.expires_on != expire_date(as_of).isoformat():
                        problems.append(f"{where}: expires_on {spec.expires_on} must be {expire_date(as_of)}")

            elif spec.type == SAVINGS_OPPORTUNITY:
                truth = bool(derived_recommendations)
                if spec.count != (len(derived_recommendations) if truth else 0):
                    problems.append(f"{where}: expected count {spec.count} conflicts with "
                                    f"spec recommendations {derived_recommendations}")
                for index, evidence_set in enumerate(spec.evidence_sets):
                    if index >= len(derived_recommendations):
                        break
                    category, latest, previous, saving = derived_recommendations[index]
                    if spec.category != category:
                        problems.append(f"{where}: category {spec.category!r} != spec {category!r}")
                    if spec.title_contains != category:
                        problems.append(f"{where}: title_contains {spec.title_contains!r} should be {category!r}")
                    for path, expected in evidence_set:
                        if path == "latest_expenses" and _decimal(expected) != latest:
                            problems.append(f"{where}: latest {expected} != spec {latest}")
                        if path == "previous_expenses" and _decimal(expected) != previous:
                            problems.append(f"{where}: previous {expected} != spec {previous}")
                        if path == "estimated_monthly_saving" and _decimal(expected) != saving:
                            problems.append(f"{where}: saving {expected} != spec {saving}")
                    if spec.period != (latest_month_window(as_of)[0].isoformat(),
                                       latest_month_window(as_of)[1].isoformat()):
                        problems.append(f"{where}: period {spec.period} != latest month window")
                    if spec.expires_on != expire_date(as_of).isoformat():
                        problems.append(f"{where}: expires_on {spec.expires_on} must be {expire_date(as_of)}")

            elif spec.type == UPCOMING_EXPENSE:
                sched = [
                    entry for entry in scenario.scheduled
                    if entry.kind == "expense" and entry.status == "scheduled"
                    and as_of <= entry.due_date <= as_of + timedelta(days=UPCOMING_HORIZON_DAYS)
                ]
                if spec.count != len(sched):
                    problems.append(f"{where}: expected count {spec.count} conflicts with "
                                    f"spec scheduled entries {sched}")
                for index, evidence_set in enumerate(spec.evidence_sets):
                    if index >= len(sched):
                        break
                    entry = sched[index]
                    if spec.period != (as_of.isoformat(), entry.due_date.isoformat()):
                        problems.append(f"{where}: period {spec.period} must reach the due date")
                    if spec.expires_on != (entry.due_date + timedelta(days=1)).isoformat():
                        problems.append(f"{where}: expires_on must be the day after the due date")
                    if not spec.plan_marked:
                        problems.append(f"{where}: scheduled obligations must be plan-marked")
                    for path, expected in evidence_set:
                        if path == "amount" and _decimal(expected) != Decimal(entry.amount):
                            problems.append(f"{where}: amount {expected} != spec {entry.amount}")
                        if path == "title" and expected != entry.title:
                            problems.append(f"{where}: title {expected!r} != spec {entry.title!r}")

            elif spec.type == PROJECTED_SHORTFALL:
                net = expected_baseline_net(scenario, as_of)
                truth = net < 0
                if spec.count != (1 if truth else 0):
                    problems.append(f"{where}: expected count {spec.count} conflicts with "
                                    f"spec baseline net {net}")
                if spec.count:
                    for path, expected in spec.evidence_sets[0]:
                        if path == "estimated_monthly_net" and _decimal(expected) != net:
                            problems.append(f"{where}: net {expected} != spec {net}")
                    if spec.period and spec.period[0] != as_of.isoformat():
                        problems.append(f"{where}: period start must be as_of")
                    if spec.expires_on != expire_date(as_of).isoformat():
                        problems.append(f"{where}: expires_on {spec.expires_on} must be {expire_date(as_of)}")

            elif spec.type == GOAL_PROGRESS:
                active = [goal for goal in scenario.goals if goal.status == "active"]
                if spec.count != len(active):
                    problems.append(f"{where}: expected count {spec.count} conflicts with "
                                    f"spec active goals {active}")
                for index, evidence_set in enumerate(spec.evidence_sets):
                    if index >= len(active):
                        break
                    goal = active[index]
                    if spec.period != (as_of.isoformat(), goal.target_date):
                        problems.append(f"{where}: period {spec.period} must span as_of..target_date")
                    if spec.expires_on != expire_date(as_of).isoformat():
                        problems.append(f"{where}: expires_on {spec.expires_on} must be {expire_date(as_of)}")
                    for path, expected in evidence_set:
                        if path == "name" and expected != goal.name:
                            problems.append(f"{where}: name {expected!r} != spec {goal.name!r}")
                        if path == "current_saved" and _decimal(expected) != Decimal(goal.current_saved):
                            problems.append(f"{where}: current_saved {expected} != spec {goal.current_saved}")

        behavior_ok = any(spec.count > 0 for spec in case.expected)
        expected_behavior = "triggered" if behavior_ok else "silent"
        if case.behavior != expected_behavior:
            problems.append(
                f"{case.case_id}: behavior {case.behavior!r} but expectations are {expected_behavior!r}"
            )
    return problems


def _decimal(value):
    try:
        return Decimal(str(value))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


def seed_insight_scenarios(db, scenarios: tuple[InsightScenario, ...]) -> list:
    """Seed the given worlds (e.g. a case scenario plus the canary) as users."""
    from uuid import uuid4
    from app.models import User, Transaction, ScheduledCashflowItem
    from app.models.savings_goal import SavingsGoal

    emails = [f"insight-{uuid4().hex}@example.com" for _ in scenarios]
    for email in emails:
        db.add(User(email=email, hashed_password="evaluation"))
    db.commit()
    users = [db.query(User).filter(User.email == email).one() for email in emails]

    for user, scenario in zip(users, scenarios):
        for tx in scenario.transactions:
            db.add(Transaction(user_id=user.id, date=tx.date, amount=Decimal(tx.amount),
                               category=tx.category, merchant=tx.merchant))
        for entry in scenario.scheduled:
            db.add(ScheduledCashflowItem(user_id=user.id, title=entry.title, kind=entry.kind,
                                         amount=Decimal(entry.amount), status=entry.status,
                                         due_date=entry.due_date))
        for goal in scenario.goals:
            db.add(SavingsGoal(user_id=user.id, name=goal.name,
                               target_amount=Decimal(goal.target_amount),
                               current_saved=Decimal(goal.current_saved),
                               target_date=date.fromisoformat(goal.target_date),
                               status=goal.status))
    db.commit()
    return users


def clear_insight_scenarios(db, users) -> None:
    """Remove seeded worlds; cascades clean their records."""
    from app.models import ScheduledCashflowItem, User
    from app.models.savings_goal import SavingsGoal
    from app.models.transactions import Transaction

    for user in users:
        db.query(ScheduledCashflowItem).filter_by(user_id=user.id).delete()
        db.query(SavingsGoal).filter_by(user_id=user.id).delete()
        db.query(Transaction).filter_by(user_id=user.id).delete()
        db.query(User).filter(User.id == user.id).delete()
    db.commit()


def validate_insight_dataset() -> list[str]:
    problems = list(insight_ground_truth_consistency())
    ids = [case.case_id for case in INSIGHT_EVALUATION_CASES]
    if len(ids) != len(set(ids)):
        problems.append("insight case ids are not unique")
    if len(ids) < len(KNOWN_INSIGHT_TYPES) * 2:
        problems.append("insight dataset lacks trigger/silent coverage")
    for case in INSIGHT_EVALUATION_CASES:
        for spec in case.expected:
            if spec.count > 0 and not spec.evidence_sets:
                problems.append(f"{case.case_id}/{spec.type}: expected insight has no evidence pins")
    return problems
