from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.finance.evidence import (
    FinanceEvidence,
    analytics_evidence,
    rag_evidence)

from app.services.finance.operations import (
    get_categories,
    get_monthly,
    get_recurring,
    get_summary,
    get_top_merchants,
)
from app.services.finance.router import (
    FinanceIntent,
    route_finance_question,
)
from app.services.rag.retrieval import retrieve_transactions


@dataclass
class FinanceQueryResult:
    intent: FinanceIntent
    evidence: list[FinanceEvidence]
    sources: list[dict]


def execute_finance_query(
    db: Session,
    question: str,
    user_id: int,
    k: int = 5) -> FinanceQueryResult:
    question = question.strip()

    if not question:
        raise ValueError("Question cannot be empty.")

    if user_id <= 0:
        raise ValueError("user_id must be positive.")

    intent = route_finance_question(question)

    if intent == FinanceIntent.UNKNOWN:
        return FinanceQueryResult(
            intent=intent,
            evidence=[],
            sources=[],
        )

    evidence: list[FinanceEvidence] = []
    sources: list[dict] = []

    if intent in (
        FinanceIntent.ANALYTICS,
        FinanceIntent.HYBRID,
    ):
        summary = get_summary(
            db,
            user_id,
        )

        categories = get_categories(
            db,
            user_id,
        )

        monthly = get_monthly(
            db,
            user_id,
        )

        top_merchants = get_top_merchants(
            db,
            user_id,
        )

        recurring = get_recurring(
            db,
            user_id,
        )

        evidence.extend(
            [
                analytics_evidence("summary", summary),
                analytics_evidence("categories", categories),
                analytics_evidence("monthly", monthly),
                analytics_evidence("top_merchants", top_merchants),
                analytics_evidence("recurring", recurring),
            ]
        )

    if intent in (
        FinanceIntent.RAG,
        FinanceIntent.HYBRID,
    ):
        transactions = retrieve_transactions(
            query=question,
            user_id=user_id,
            k=k,
        )

        rag_data = [
            {
                "content": transaction.content,
                "metadata": transaction.metadata,
            }
            for transaction in transactions
        ]

        evidence.append(
            rag_evidence(rag_data)
        )

        sources = [
            {
                "transaction_id": transaction.metadata.get("transaction_id"),
                "date": transaction.metadata.get("date"),
                "merchant": transaction.metadata.get("merchant"),
                "category": transaction.metadata.get("category"),
                "amount": transaction.metadata.get("amount"),
            }
            for transaction in transactions
        ]

    return FinanceQueryResult(
        intent=intent,
        evidence=evidence,
        sources=sources,
    )