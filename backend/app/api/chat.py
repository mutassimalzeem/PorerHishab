from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.chat import (
    FinanceQuestionRequest,
    FinanceQuestionResponse,
)
from app.services.finance.service import answer_finance_query


router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)


@router.post(
    "/ask",
    response_model=FinanceQuestionResponse,
)
def ask_finance_question(
    payload: FinanceQuestionRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = answer_finance_query(
            db=db,
            question=payload.question,
            user_id=current.id,
            k=payload.k,
        )

        return FinanceQuestionResponse(
            answer=result.answer,
            intent=result.intent.value,
            sources=result.sources,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )