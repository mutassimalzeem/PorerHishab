"""Deterministic, offline-reproducible finance scenario for evaluation.

The scenario is the evaluation's "source of truth": a small fixed set of
users, transactions, and scheduled cashflow entries. Ground truth numbers are
computed from this specification with plain Python arithmetic, deliberately
*independent* of the coach's SQL aggregation path.
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

# Fixed evaluation "today". Tests pass this to the coach, so results are
# reproducible down to the matched-day comparison logic.
AS_OF = date(2026, 10, 25)

# If any evaluation answer contains this merchant phrase, user isolation has
# been broken: it only exists on another user's records.
ISOLATION_CANARY = "SECRET OTHER USER LEDGER"


@dataclass(frozen=True)
class ScenarioTransaction:
    date: date
    amount: str  # decimal string; positive = income, negative = expense
    category: str
    merchant: str


@dataclass(frozen=True)
class ScheduledEntry:
    title: str
    kind: str  # "expense" | "income"
    amount: str
    status: str  # "scheduled" | "paid" | "cancelled" | "overdue"
    due_date: date


@dataclass(frozen=True)
class FinanceScenario:
    transactions: tuple[tuple[ScenarioTransaction, ...], ...]
    scheduled: tuple[tuple[ScheduledEntry, ...], ...]

    def user_count(self):
        return len(self.transactions)


# ---------------------------------------------------------------------------
# Scenario blueprint
#
# User A history: three complete calendar months (July, August, September)
# plus a partial current month (October 1..25), each month for the same user.
#   July  : +30000 salary, -3500 food, -1500 shopping -> expenses 5000
#   August: +30000 salary, -3800 food, -1200 shopping -> expenses 5000
#   Sept  : +30000 salary, -4000 food, -2000 shopping, -2500 bills -> 8500
#   Oct 1-25: +30000 salary, -5000 food, -3000 shopping -> expenses 8000
#
# Scheduled items for User A (as_of-relative):
#   expense 6000 "Internet bill"       due 2026-10-28 scheduled
#   income  15000 "Freelance payment"  due 2026-10-30 scheduled
#   expense 9000 "Old rent"            due 2026-10-26 paid (must be excluded)
#
# User B owns one large secret transaction in September. Every evaluation
# case asked as User A must neither mix that amount into aggregates nor leak
# the merchant string into any response text.
# ---------------------------------------------------------------------------


def _user_a_transactions():
    def tx(iso, amount, category, merchant):
        return ScenarioTransaction(date.fromisoformat(iso), amount, category, merchant)

    return (
        tx("2026-07-05", "30000", "Salary", "Acme Corp Payroll"),
        tx("2026-07-10", "-3500", "Food", "Dhaka Biryani House"),
        tx("2026-07-12", "-1500", "Shopping", "Aarong"),
        tx("2026-08-04", "30000", "Salary", "Acme Corp Payroll"),
        tx("2026-08-09", "-3800", "Food", "Dhaka Biryani House"),
        tx("2026-08-16", "-1200", "Shopping", "Aarong"),
        tx("2026-09-05", "30000", "Salary", "Acme Corp Payroll"),
        tx("2026-09-06", "-4000", "Food", "Dhaka Biryani House"),
        tx("2026-09-12", "-2000", "Shopping", "Aarong"),
        tx("2026-09-15", "-2500", "Bills", "DESCO Electricity"),
        tx("2026-10-05", "30000", "Salary", "Acme Corp Payroll"),
        tx("2026-10-06", "-5000", "Food", "Dhaka Biryani House"),
        tx("2026-10-10", "-3000", "Shopping", "Aarong"),
    )


EVALUATION_SCENARIO = FinanceScenario(
    transactions=(tuple(_user_a_transactions()), (
        ScenarioTransaction(date(2026, 9, 8), "-999999", "Food", ISOLATION_CANARY),
    )),
    scheduled=(
        (
            ScheduledEntry("Internet bill", "expense", "6000", "scheduled", AS_OF + timedelta(days=3)),
            ScheduledEntry("Freelance payment", "income", "15000", "scheduled", AS_OF + timedelta(days=5)),
            ScheduledEntry("Old rent", "expense", "9000", "paid", AS_OF + timedelta(days=1)),
        ),
        (),
    ),
)


def scenario_totals(scenario: FinanceScenario, user_index: int, start: date, end: date, category: str | None = None) -> dict[str, Decimal]:
    """Ground truth income/expenses for one user, computed from the spec.

    Follows the storage convention (expenses stored negative) but performs its
    own arithmetic: it never calls the coach or its SQL helpers.
    """
    if start > end:
        raise ValueError("Invalid ground truth range")
    income = Decimal("0")
    expenses = Decimal("0")
    for tx in scenario.transactions[user_index]:
        if not (start <= tx.date <= end):
            continue
        if category is not None and tx.category.lower() != category.lower():
            continue
        amount = Decimal(tx.amount)
        if amount > 0:
            income += amount
        else:
            expenses += -amount
    return {"income": income, "expenses": expenses}


def scenario_scheduled_expenses(scenario: FinanceScenario, user_index: int, start: date, end: date) -> Decimal:
    """Ground truth sum of scheduled (status='scheduled') expenses in a range."""
    total = Decimal("0")
    for entry in scenario.scheduled[user_index]:
        if entry.kind == "expense" and entry.status == "scheduled" and start <= entry.due_date <= end:
            total += Decimal(entry.amount)
    return total


def seed_scenario(db, scenario: FinanceScenario = EVALUATION_SCENARIO) -> list:
    """Seed the scenario into the database and return the created users.

    Records are attached to the created users; cleanup is done via
    :func:`clear_scenario` (deleting users cascades to their records).
    """
    from uuid import uuid4
    from app.models import User, Transaction, ScheduledCashflowItem

    emails = [f"eval-{index}-{uuid4().hex}@example.com" for index in range(scenario.user_count())]
    for email in emails:
        db.add(User(email=email, hashed_password="evaluation"))
    db.commit()
    users = [db.query(User).filter(User.email == email).one() for email in emails]

    for user_index, person in enumerate(users):
        for tx in scenario.transactions[user_index]:
            db.add(Transaction(user_id=person.id, date=tx.date,
                               amount=Decimal(tx.amount), category=tx.category,
                               merchant=tx.merchant))
        for entry in scenario.scheduled[user_index]:
            db.add(ScheduledCashflowItem(user_id=person.id, title=entry.title,
                                         kind=entry.kind, amount=Decimal(entry.amount),
                                         status=entry.status, due_date=entry.due_date))
    db.commit()
    return users


def clear_scenario(db, users: list) -> None:
    """Remove users created by :func:`seed_scenario` along with their records."""
    from app.models import User, ScheduledCashflowItem

    for person in users:
        db.query(ScheduledCashflowItem).filter_by(user_id=person.id).delete()
        db.delete(person)
    db.commit()
