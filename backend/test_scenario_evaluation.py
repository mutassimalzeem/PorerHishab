"""Eight offline evaluations. Expected claims use independent plain arithmetic.

Fixture: 30,000 income, 5,000 expenses, 100,000 verified cash. AI-15P protects
November plus December 1: 5000 + round(5000/31,2) = 5161.29; capacity is
30000*.8 - 5161.29 - 2400 = 16438.71. No engine generates expected values.
"""
from datetime import date
from decimal import Decimal as D
import pytest
from test_goal_planning import data, seed, DAY, request as plan_request
from test_scenarios import change,setup,run,metrics
from app.services.finance import goal_planning as p

CASES=[
    ("rent_increase","recurring_expense_adjustment","3000","monthly_savings_capacity","13438.71"),
    ("income_decrease","income_adjustment","-5000","monthly_savings_capacity","12838.71"),
    ("income_increase","income_adjustment","5000","monthly_savings_capacity","20038.71"),
    ("subscription","recurring_expense_adjustment","500","monthly_savings_capacity","15938.71"),
    ("large_purchase","one_time_expense","60000","projected_end_cash",None),
    ("savings_increase","savings_contribution_adjustment","3000","monthly_savings_capacity","13438.71"),
]
@pytest.mark.parametrize("name,kind,amount,metric,expected",CASES,ids=[r[0] for r in CASES])
def test_structured_claims(data,name,kind,amount,metric,expected):
    db,users=data;seed(db,users[0]);scenario=setup(db,users[0],[change(kind,amount)])
    m=metrics(run(db,users[0],scenario))[metric]
    if expected is None:assert m.absolute_delta==D("-60000")
    else:assert m.scenario_value==D(expected)

def test_emergency_deadline(data):
    db,users=data;goal=seed(db,users[0]);scenario=setup(db,users[0],[change("goal_target_date_adjustment",target_id=goal.id,target_date=date(2027,1,31))])
    result=run(db,users[0],scenario)
    assert result.baseline_goals[0]["required_contribution"]=="1666.67"
    assert result.scenario_goals[0]["required_contribution"]=="3333.34"

def test_competing_goal_pressure(data):
    db,users=data;first=seed(db,users[0]);p.create_plan(db,users[0].id,first.id,plan_request(),as_of=DAY)
    second=seed(db,users[0],target="100000",priority=5)
    scenario=setup(db,users[0],[change("goal_commitment_adjustment","15000",target_id=first.id)])
    result=run(db,users[0],scenario)
    other=next(g for g in result.scenario_goals if g["goal_id"]==second.id)
    assert other["projected_contribution_capacity"]=="1438.71"
    assert other["feasibility"]=="not_currently_feasible"
