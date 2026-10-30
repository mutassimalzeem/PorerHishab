"""Actual ASGI routes, real SQL/engine, isolated in-memory database."""
from datetime import date
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.database import Base, get_db
from app.main import app
from app.models import User, Transaction, ScheduledCashflowItem
from app.api.auth import create_access_token

@pytest.fixture
def api_world(monkeypatch):
    import app.api.intelligence as route
    monkeypatch.setattr(route, 'today_dhaka', lambda: date(2026,10,25))
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db=sessionmaker(bind=engine)()
    users=[User(email=f'intelligence{i}@example.com',hashed_password='unused') for i in range(2)]
    db.add_all(users);db.commit()
    def override(): yield db
    previous=app.dependency_overrides.copy();app.dependency_overrides[get_db]=override
    headers=[{'Authorization':'Bearer '+create_access_token({'sub':u.email,'user_id':u.id})} for u in users]
    try:
        with TestClient(app) as client: yield client,db,users,headers
    finally:
        app.dependency_overrides.clear();app.dependency_overrides.update(previous)
        db.close();engine.dispose()

def test_intelligence_requires_auth(api_world):
    client,*_=api_world
    assert client.get('/finance/intelligence').status_code==401

def test_unknown_is_not_zero_and_public_payload_hides_internal_id(api_world):
    client,db,users,headers=api_world
    response=client.get('/finance/intelligence',headers=headers[0])
    assert response.status_code==200,response.text
    body=response.json();snapshot=body['snapshot']
    assert snapshot['income'] is None and snapshot['net_cashflow'] is None
    assert snapshot['data_coverage']['status']=='no_records'
    assert snapshot['history']['baseline'] is None
    assert body['cashflow']['forecast_net'] is None
    assert all(row['income'] is None for row in body['monthly_history'])
    assert 'user_id' not in response.text

def test_engine_output_preserves_decimals_plans_coverage_and_isolation(api_world):
    client,db,users,headers=api_world
    for month in (7,8,9,10):
        db.add_all([Transaction(user_id=users[0].id,date=date(2026,month,5),amount=Decimal('30000.25'),category='Salary'),Transaction(user_id=users[0].id,date=date(2026,month,6),amount=Decimal('-1500.10'),category='Food',merchant='Local shop')])
    db.add(Transaction(user_id=users[1].id,date=date(2026,10,6),amount=Decimal('-999999.99'),category='Secret category',merchant='SECRET CANARY'))
    db.add_all([ScheduledCashflowItem(user_id=users[0].id,title='Expected payment',kind='income',amount=Decimal('9000'),due_date=date(2026,10,28)),ScheduledCashflowItem(user_id=users[0].id,title='Paid plan',kind='expense',status='paid',amount=Decimal('800'),due_date=date(2026,10,28))]);db.commit()
    response=client.get('/finance/intelligence',headers=headers[0]);assert response.status_code==200,response.text
    body=response.json();assert body['snapshot']['net_cashflow']=='28500.15'
    assert body['snapshot']['data_coverage']['is_adequate'] is True
    assert body['snapshot']['scheduled_obligations']['uncertain_scheduled_income']=='9000.00'
    assert body['snapshot']['scheduled_obligations']['scheduled_expenses']=='0.00'
    assert body['category_comparisons'][0]['delta']=='0.00'
    assert len(body['monthly_history'])==3
    assert 'SECRET CANARY' not in response.text and '999999' not in response.text
    assert body==client.get('/finance/intelligence',headers=headers[0]).json()

def test_existing_frontend_read_and_mutation_contracts(api_world):
    client,db,users,headers=api_world;h=headers[0]
    tx=client.post('/transactions',headers=h,json={'date':'2026-10-20','amount':'-250.50','description':'Tea','category':'Food'})
    assert tx.status_code==201,tx.text
    ident=tx.json()['id']
    assert client.patch(f'/transactions/{ident}/category',headers=h,json={'category':'Groceries'}).json()['category']=='Groceries'
    for path in ['/me','/transactions?limit=20&offset=0&category=Groceries','/insights/summary?start_date=2026-10-01&end_date=2026-10-25','/insights/monthly','/insights/proactive','/finance/savings/recommendations']:
        result=client.get(path,headers=h);assert result.status_code==200,(path,result.text)
    scheduled=client.post('/finance/scheduled-cashflow',headers=h,json={'title':'Internet','kind':'expense','amount':'1500.00','due_date':'2026-10-28'})
    assert scheduled.status_code==201,scheduled.text
    ident=scheduled.json()['id']
    assert client.get('/finance/scheduled-cashflow?status=scheduled',headers=h).json()['total']==1
    assert client.patch(f'/finance/scheduled-cashflow/{ident}',headers=h,json={'status':'paid'}).status_code==200
    # A distant date avoids wall-clock-dependent target validation.
    goal=client.post('/finance/goals',headers=h,json={'name':'Reserve','target_amount':'12000.00','current_saved':None,'target_date':'2099-12-31'})
    assert goal.status_code==201,goal.text
    ident=goal.json()['id']
    assert client.get(f'/finance/goals/{ident}/plan',headers=h).json()['required_monthly'] is None
    assert client.patch(f'/finance/goals/{ident}',headers=h,json={'current_saved':'1000.00'}).status_code==200
    assert client.get('/finance/goals',headers=h).json()['total']==1
    for path,payload in [('/finance/coach/cashflow',{'starting_balance':'10000.00','months_ahead':3}),('/finance/coach/spending-decision',{'starting_balance':'10000.00','purchase_amount':'500.00','safety_buffer':'3000.00','horizon_days':30}),('/chat/ask',{'question':'What bills are coming up?'})]:
        result=client.post(path,headers=h,json=payload);assert result.status_code==200,(path,result.text)
    assert client.get('/finance/goals',headers=headers[1]).json()['total']==0


def test_auth_refresh_and_csv_use_actual_routes_without_external_database(api_world, monkeypatch):
    client,db,users,headers=api_world
    import app.services.transaction_service as service
    # The legacy CSV service owns a session factory; bind it to this test's
    # in-memory database rather than the developer's configured database.
    monkeypatch.setattr(service, 'SessionLocal', sessionmaker(bind=db.get_bind()))
    registration=client.post('/register',json={'email':'new-frontend@example.com','password':'test-only-password','full_name':'Frontend Test'})
    assert registration.status_code==200,registration.text
    login=client.post('/login',json={'email':'new-frontend@example.com','password':'test-only-password'})
    assert login.status_code==200,login.text
    refresh=client.post('/refresh',data={'refresh_token':login.json()['refresh_token']})
    assert refresh.status_code==200,refresh.text
    auth={'Authorization':'Bearer '+refresh.json()['access_token']}
    assert client.get('/me',headers=auth).json()['full_name']=='Frontend Test'
    uploaded=client.post('/upload-csv',headers=auth,files={'file':('test.csv','date,amount,description,category\n2026-10-20,-250.50,Tea,Food\n','text/csv')})
    assert uploaded.status_code==200,uploaded.text
    rows=client.get('/transactions',headers=auth).json()
    assert rows['total']==1 and rows['items'][0]['amount']=='-250.50'


def test_generated_frontend_contracts_match_the_actual_openapi():
    from pathlib import Path
    from scripts.generate_frontend_contracts import generate
    target=Path(__file__).resolve().parents[1]/'frontend/src/generated/api.ts'
    assert target.read_text(encoding='utf-8')==generate(), 'Run scripts/generate_frontend_contracts.py'


def test_auth_and_csv_routes_publish_explicit_response_contracts():
    spec = app.openapi()
    expected = {
        "/register": "RegisterTokenResponse",
        "/login": "LoginTokenResponse",
        "/refresh": "RefreshTokenResponse",
        "/upload-csv": "CSVUploadResponse",
    }
    for path, schema_name in expected.items():
        response_schema = (
            spec["paths"][path]["post"]["responses"]["200"]
            ["content"]["application/json"]["schema"]
        )
        assert response_schema["$ref"].endswith(schema_name)

    schemas = spec["components"]["schemas"]
    assert set(schemas["RegisterTokenResponse"]["properties"]) == {
        "access_token",
        "token_type",
    }
    assert set(schemas["LoginTokenResponse"]["properties"]) == {
        "access_token",
        "refresh_token",
        "token_type",
    }
    assert set(schemas["RefreshTokenResponse"]["properties"]) == {
        "access_token",
        "token_type",
    }
