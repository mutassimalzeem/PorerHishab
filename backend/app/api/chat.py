"""Grounded date-aware finance questions; no provider or vector database required."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.chat import FinanceQuestionRequest, FinanceQuestionResponse
from app.services.finance.grounded_chat import answer_question, AmbiguousQuestion

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/ask", response_model=FinanceQuestionResponse)
def ask_finance_question(payload: FinanceQuestionRequest, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return answer_question(db, current.id, payload)
    except AmbiguousQuestion as exc:
        raise HTTPException(422, str(exc)) from None
