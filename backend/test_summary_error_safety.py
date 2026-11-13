"""Summary HTTP/error contracts; synthetic users and no database/provider I/O."""
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from app import main

ROUTES = [
    ("/summary", "Summary unavailable", "summary_request_failed", 10000),
    ("/categories/summary", "Category summary unavailable", "category_summary_request_failed", 100000),
]
SENSITIVE = (
    "INTERNAL_MARKER postgres://fixture:dummy-password@private/db "
    "token=dummy-token fixture@example.invalid balance=987654.32 "
    "provider-body=private-provider-data SELECT private_column FROM private_table"
)


@pytest.fixture
def client(monkeypatch):
    previous = main.app.dependency_overrides.copy()
    session = object()
    main.app.dependency_overrides[main.get_db] = lambda: session
    main.app.dependency_overrides[main.get_current_user] = lambda: SimpleNamespace(id=42)
    repository = Mock(return_value=[])
    monkeypatch.setattr(main, "list_transactions", repository)
    try:
        with TestClient(main.app) as http:
            yield http, repository, session
    finally:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(previous)


@pytest.mark.parametrize("path,detail,event,limit", ROUTES)
@pytest.mark.parametrize("error_type", [RuntimeError, ValueError, SQLAlchemyError])
@pytest.mark.parametrize("site", ["repository", "dataframe"])
def test_unexpected_errors_are_generic_and_logs_are_safe(
    client, monkeypatch, caplog, path, detail, event, limit, error_type, site
):
    http, repository, session = client
    failure = error_type(SENSITIVE)
    if site == "repository":
        repository.side_effect = failure
    else:
        monkeypatch.setattr(main.pd, "DataFrame", Mock(side_effect=failure))
    caplog.set_level(logging.ERROR, logger=main.__name__)
    response = http.get(path)
    assert response.status_code == 500
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"detail": detail}
    repository.assert_called_once_with(db=session, limit=limit, user_id=42)
    records = [record for record in caplog.records if record.name == main.__name__]
    assert [record.getMessage() for record in records] == [event]
    assert all(record.args == () and record.exc_info is None and record.stack_info is None
               for record in records)
    for marker in SENSITIVE.split():
        assert marker not in response.text and marker not in caplog.text


@pytest.mark.parametrize("path,detail,event,limit", ROUTES)
def test_exception_string_is_never_evaluated(client, caplog, path, detail, event, limit):
    class UnsafeStringError(Exception):
        def __str__(self):
            raise AssertionError("Exception payload must not be formatted")
    http, repository, _ = client
    repository.side_effect = UnsafeStringError()
    caplog.set_level(logging.ERROR, logger=main.__name__)
    response = http.get(path)
    assert response.status_code == 500
    assert response.json() == {"detail": detail}
    assert event in caplog.text


@pytest.mark.parametrize("path,detail,event,limit", ROUTES)
@pytest.mark.parametrize("site", ["dependency", "repository"])
@pytest.mark.parametrize("status,expected,headers", [
    (400, "Invalid summary request", {}),
    (422, [{"loc": ["query", "synthetic"], "msg": "Invalid value", "type": "value_error"}], {}),
    (429, "Too many requests", {"Retry-After": "60"}),
])
def test_expected_http_errors_keep_contract(
    client, caplog, path, detail, event, limit, site, status, expected, headers
):
    http, repository, _ = client
    def fail():
        raise HTTPException(status_code=status, detail=expected, headers=headers)
    if site == "dependency":
        main.app.dependency_overrides[main.get_current_user] = fail
    else:
        repository.side_effect = HTTPException(status_code=status, detail=expected, headers=headers)
    response = http.get(path)
    assert response.status_code == status and response.json() == {"detail": expected}
    for key, value in headers.items():
        assert response.headers[key] == value
    assert not [record for record in caplog.records if record.name == main.__name__]
    if site == "dependency":
        repository.assert_not_called()


@pytest.mark.parametrize("path,detail,event,limit", ROUTES)
@pytest.mark.parametrize("authorization", [None, "Bearer invalid-synthetic-token"])
def test_authentication_errors_do_not_reach_summary(client, path, detail, event, limit, authorization):
    http, repository, _ = client
    main.app.dependency_overrides.pop(main.get_current_user)
    headers = {} if authorization is None else {"Authorization": authorization}
    response = http.get(path, headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated" if authorization is None else "Invalid or expired token"}
    repository.assert_not_called()


@pytest.mark.parametrize("path,detail,event,limit", ROUTES)
@pytest.mark.parametrize("populated", [False, True])
def test_successful_summary_contract_and_owner_scope(client, path, detail, event, limit, populated):
    http, repository, session = client
    if populated:
        repository.return_value = [
            {"amount": 100.0, "category": "Income"},
            {"amount": -25.0, "category": "Food"},
        ]
    response = http.get(path)
    assert response.status_code == 200
    if path == "/summary":
        expected = {"total_income": 100.0, "total_expenses": -25.0, "balance": 75.0} if populated else {
            "total_income": 0.0, "total_expenses": 0.0, "balance": 0.0}
    else:
        expected = {
            "income_by_category": {"Income": 100.0} if populated else {},
            "expenses_by_category": {"Food": -25.0} if populated else {},
            "net_by_category": {"Food": -25.0, "Income": 100.0} if populated else {},
            "grand_totals": {"income": 100.0, "expenses": -25.0, "net": 75.0} if populated else {
                "income": 0.0, "expenses": 0.0, "net": 0.0},
        }
    assert response.json() == expected
    repository.assert_called_once_with(db=session, limit=limit, user_id=42)
