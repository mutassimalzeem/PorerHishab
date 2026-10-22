from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.chat import (
    FinanceQuestionRequest,
    FinanceQuestionResponse)
from app.services.rag.qa import answer_finance_question


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/ask",
    response_model=FinanceQuestionResponse)


def ask_finance_question(
    payload: FinanceQuestionRequest,
    current: User = Depends(get_current_user)):
    
    try:
        result = answer_finance_question(
            question=payload.question,
            user_id=current.id,
            k=payload.k,
        )

        return FinanceQuestionResponse(
            answer=result.answer,
            sources=result.sources,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )