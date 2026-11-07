"""Seed only the explicitly named, local disposable review E2E database."""
import os
import sys
from pathlib import Path
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def validate_database(url):
    parsed = make_url(url)
    if (parsed.get_backend_name() != "postgresql"
            or parsed.host not in {"localhost", "127.0.0.1"}
            or parsed.database != "porerhishab_review_e2e"
            or parsed.username != "review_e2e"
            or os.environ.get("REVIEW_E2E_DISPOSABLE") != "1"):
        raise ValueError("Refusing seed: requires explicit disposable local review E2E database")


def main():
    validate_database(os.environ.get("DATABASE_URL", "sqlite://"))
    from app.core.database import SessionLocal
    from app.api.auth import get_password_hash
    from app.models import User, Account, Transaction, SavingsGoal, ScheduledCashflowItem

    with SessionLocal() as db:
        for email in ["review@example.com", "other@example.com"]:
            if db.query(User).filter_by(email=email).first():
                continue
            user = User(email=email, hashed_password=get_password_hash("Review-E2E-only-123!"))
            db.add(user)
            db.flush()
            if email.startswith("other"):
                continue
            db.add(Account(user_id=user.id, name="Synthetic review cash", currency="BDT",
                           opening_balance=Decimal("0"), opening_balance_date=date(2026, 11, 1),
                           current_balance=Decimal("0"), balance_as_of=datetime(2026, 11, 1, tzinfo=timezone.utc)))
            for month in [8, 9, 10]:
                db.add(Transaction(user_id=user.id, date=date(2026, month, 2), amount=Decimal("30000")))
                db.add(Transaction(user_id=user.id, date=date(2026, month, 3), amount=Decimal("-5000"), category="food"))
            db.add(SavingsGoal(user_id=user.id, name="Synthetic laptop", target_amount=Decimal("10000"),
                               current_saved=Decimal("0"), target_date=date(2027, 4, 30)))
            db.add(ScheduledCashflowItem(user_id=user.id, title="Synthetic rent", kind="expense",
                                        amount=Decimal("9000"), due_date=date(2026, 11, 10), status="scheduled"))
        db.commit()


if __name__ == "__main__":
    main()
