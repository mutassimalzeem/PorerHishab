"""CSV regression coverage uses a private in-memory database per test."""
from datetime import date
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.dependencies import get_current_user
from app.main import app
from app.models import Transaction, User
from app.services import transaction_service
from app.services.transaction_service import _parse_amount


@pytest.fixture
def upload(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        user = User(email="csv@example.test", hashed_password="unused")
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: db
        monkeypatch.setattr(transaction_service, "SessionLocal", factory)
        try:
            yield TestClient(app), db, user_id
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)
    engine.dispose()


@pytest.mark.parametrize("raw,expected", [
    ("1234.56", D("1234.56")), ("1,234.56", D("1234.56")),
    ("-250.50", D("-250.50")), ("0", D("0")), ("0.10", D("0.10")),
    ("1.2300", D("1.23")), ("", None), (None, None), ("invalid", None),
    ("1.001", None), ("NaN", None), ("Infinity", None),
    ("1000000000000", None), ("1,23", None), (True, None),
])
def test_amount_policy(raw, expected):
    assert _parse_amount(raw) == expected


def test_partial_import_counts_totals_and_repeated_upload(upload):
    client, db, user_id = upload
    csv = ('date,amount,category\n2026-11-01,1234.56,Income\n'
           '2026-11-01,-250.50,Food\n2026-11-01,0,Other\n'
           '2026-11-01,"1,234.56",Income\n2026-11-01,0.10,Income\n'
           '2026-11-01,,Other\n2026-11-01,invalid,Other\n'
           'invalid,50,Other\n2026-11-01,1.001,Other\n')
    def post():
        return client.post("/upload-csv", files={"file": ("rows.csv", csv, "text/csv")})
    response = post()
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["records"], result["rows_received"], result["rows_persisted"],
            result["rows_rejected"], result["rows_skipped"]) == (5, 9, 5, 4, 0)
    assert [(e["row"], e["field"]) for e in result["errors"]] == [
        (7, "amount"), (8, "amount"), (9, "date"), (10, "amount")]
    assert result["total_income"] == 2469.22
    assert result["total_expenses"] == -250.50
    assert result["balance"] == 2218.72
    rows = db.scalars(select(Transaction).where(Transaction.user_id == user_id)).all()
    assert sorted(t.amount for t in rows) == sorted(map(D, ["1234.56", "-250.50", "0", "1234.56", "0.10"]))
    from app.services.intelligence.facts import totals
    actual = totals(db, user_id, date(2026, 11, 1), date(2026, 11, 30))
    assert actual["income"] == D("2469.22")
    assert actual["expenses"] == D("250.50")
    from app.services.finance.financial_coach_evidence import FinancialCoachEvidenceAssembler
    from app.services.finance.financial_coach_router import route_financial_coach_question
    package = FinancialCoachEvidenceAssembler(db, user_id, as_of=date(2026, 11, 1)).assemble(
        route_financial_coach_question("How much did I spend this month?"), "How much did I spend this month?")
    assert package.get_evidence_by_id("ev_spending_tx_count").value == 5
    assert package.get_evidence_by_id("ev_spending_total_expenses").value == D("250.50")
    # CSV has no external transaction identifier: repeated uploads append duplicates.
    assert post().json()["rows_persisted"] == 5
    assert len(db.scalars(select(Transaction)).all()) == 10


@pytest.mark.parametrize("csv", ["date,amount\n2026-11-01,invalid\n", "date,amount\n"])
def test_all_rejected_or_header_only(upload, csv):
    client, db, _ = upload
    response = client.post("/upload-csv", files={"file": ("rows.csv", csv)})
    assert response.status_code == 200, response.text
    assert response.json()["rows_persisted"] == 0
    assert response.json()["balance"] == 0
    assert not db.scalars(select(Transaction)).all()


@pytest.mark.parametrize("csv", ["amount\n12\n", "date\n2026-11-01\n", ""])
def test_missing_columns_or_empty_file_is_client_error(upload, csv):
    response = upload[0].post("/upload-csv", files={"file": ("rows.csv", csv)})
    assert response.status_code == 400


def test_persistence_failure_does_not_report_success(upload, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("private database failure")
    monkeypatch.setattr("app.main.save_transactions", fail)
    response = upload[0].post("/upload-csv", files={"file": ("rows.csv", "date,amount\n2026-11-01,0\n")})
    assert response.status_code == 500
    assert "private" not in response.text


@pytest.mark.parametrize("raw,expected", [
    ("999999999999.99", D("999999999999.99")),
    ("-999999999999.99", D("-999999999999.99")),
    ("1000000000000.00", None), ("-1000000000000.00", None),
    ("0.001", None), ("-0.001", None), (float("nan"), None),
    (float("inf"), None), (float("-inf"), None), ("-Infinity", None),
])
def test_precision_and_nonfinite_boundaries(raw, expected):
    assert _parse_amount(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("2026-11-06", date(2026, 11, 6)), ("2024-02-29", date(2024, 2, 29)),
    ("1900-01-01", date(1900, 1, 1)),
    ("06/11/2026", None), ("11/06/2026", None), ("2026/11/06", None),
    ("2026-02-29", None), ("2026-02-30", None), ("2026-13-01", None),
    ("2026-00-10", None), ("2026-11-00", None), ("2026-1-1", None),
    ("1899-12-31", None), ("tomorrow", None), (None, None), (123, None),
])
def test_explicit_iso_date_policy(raw, expected):
    from app.services.transaction_service import _parse_date
    assert _parse_date(raw) == expected


def test_ambiguous_and_invalid_calendar_rows_are_rejected(upload):
    csv = ("date,amount\n2026-11-06,1.00\n06/11/2026,2.00\n"
           "2026-02-30,3.00\n2026-13-01,4.00\nnot-a-date,5.00\n2024-02-29,0\n")
    response = upload[0].post("/upload-csv", files={"file": ("dates.csv", csv)})
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["rows_received"], result["rows_persisted"], result["rows_rejected"], result["rows_skipped"]) == (6, 2, 4, 0)
    assert result["total_income"] == 1
    assert result["balance"] == 1
    assert all("YYYY-MM-DD" in error["message"] for error in result["errors"])


def test_upload_summary_uses_actual_database_values(upload, monkeypatch):
    client, db, _ = upload
    real_create = transaction_service.create_transactions
    def persist_changed_amount(session, transactions):
        # Simulate a database-side canonical value and ensure the response is
        # built from returned/refreshed rows, never the pre-save dataframe.
        transactions[0].amount = D("9.87")
        return real_create(session, transactions)
    monkeypatch.setattr(transaction_service, "create_transactions", persist_changed_amount)
    result = client.post("/upload-csv", files={"file": ("rows.csv", "date,amount\n2026-11-01,1.23\n")} ).json()
    assert result["rows_persisted"] == 1
    assert result["total_income"] == result["balance"] == 9.87
    assert D(str(result["preview"][0]["amount"])) == D("9.87")
    assert db.scalar(select(Transaction.amount)) == D("9.87")


def test_database_commit_failure_rolls_back_import(upload, monkeypatch):
    def failed_commit(self):
        raise RuntimeError("private commit failure")
    from sqlalchemy.orm import Session
    monkeypatch.setattr(Session, "commit", failed_commit)
    response = upload[0].post("/upload-csv", files={"file": ("rows.csv", "date,amount\n2026-11-01,0\n")})
    assert response.status_code == 500
    assert "private" not in response.text
    assert not upload[1].scalars(select(Transaction)).all()
