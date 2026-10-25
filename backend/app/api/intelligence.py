"""Read-only user-scoped adapter for the existing deterministic engine."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.intelligence import IntelligenceResponse
from app.services.intelligence.engine import build_financial_intelligence
from app.services.intelligence.categories import category_spending_facts
from app.services.intelligence.periods import today_dhaka, latest_complete_month_period, previous_complete_month_period

router = APIRouter(prefix='/finance', tags=['intelligence'])

@router.get('/intelligence', response_model=IntelligenceResponse)
def financial_intelligence(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    as_of = today_dhaka()
    result = build_financial_intelligence(db, current.id, as_of)
    payload = result.to_dict()
    # The engine's baseline is internal diagnostic output. Do not expose a
    # zero-valued estimate when its own coverage gate says it is unavailable.
    if not result.snapshot.history.adequate:
        payload['snapshot']['history']['baseline'] = None
    payload['monthly_history'] = [
        {'month': row['coverage']['start_date'][:7], 'income': row['income'],
         'expenses': row['expenses'], 'net': row['net'],
         'transaction_count': row['coverage']['transaction_count']}
        for row in result.snapshot.history.monthly
    ]
    payload['category_comparisons'] = [row.to_dict() for row in category_spending_facts(
        db, current.id, latest_complete_month_period(as_of), previous_complete_month_period(as_of))]
    return payload
