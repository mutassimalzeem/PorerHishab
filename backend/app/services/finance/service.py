from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.finance.answer import generate_finance_answer
from app.services.finance.formatting import format_finance_evidence
from app.services.finance.query import execute_finance_query
from app.services.finance.router import FinanceIntent


@dataclass
class FinanceResponse:
    answer: str
    intent: FinanceIntent
    sources: list[dict]


def answer_finance_query(
    db: Session,
    question: str,
    user_id: int,
    k: int = 5,
) -> FinanceResponse:
    result = execute_finance_query(
        db=db,
        question=question,
        user_id=user_id,
        k=k,
    )

    if result.intent == FinanceIntent.UNKNOWN:
        return FinanceResponse(
            answer=(
                "I can help with questions about your spending, "
                "income, transactions, budgets, merchants, and "
                "saving patterns."
            ),
            intent=result.intent,
            sources=[],
        )

    evidence_text = format_finance_evidence(
        result.evidence
    )

    answer = generate_finance_answer(
        question=question,
        evidence_text=evidence_text,
    )

    return FinanceResponse(
        answer=answer,
        intent=result.intent,
        sources=result.sources,
    )