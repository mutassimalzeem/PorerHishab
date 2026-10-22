from __future__ import annotations

from enum import Enum


class FinanceIntent(str, Enum):
    ANALYTICS = "analytics"
    RAG = "rag"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


ANALYTICS_PATTERNS = (
    "how much",
    "how many",
    "total",
    "spending",
    "spent",
    "expense",
    "expenses",
    "income",
    "earned",
    "monthly",
    "category",
    "categories",
    "compare",
    "highest",
    "lowest",
    "top merchant",
    "most expensive",
    "budget",
)

HYBRID_PATTERNS = (
    "why",
    "should i",
    "what should",
    "how can i save",
    "what can i cut",
    "overspending",
    "saving goal",
    "save more",
    "reduce my spending",
)

RAG_PATTERNS = (
    "where",
    "merchant",
    "transaction",
    "transactions",
    "usually",
    "habit",
    "habits",
    "pattern",
    "patterns",
    "often",
)


def route_finance_question(question: str) -> FinanceIntent:
    question = question.strip().lower()

    if not question:
        raise ValueError("Question cannot be empty.")

    if any(pattern in question for pattern in HYBRID_PATTERNS):
        return FinanceIntent.HYBRID

    if any(pattern in question for pattern in ANALYTICS_PATTERNS):
        return FinanceIntent.ANALYTICS

    if any(pattern in question for pattern in RAG_PATTERNS):
        return FinanceIntent.RAG

    return FinanceIntent.UNKNOWN