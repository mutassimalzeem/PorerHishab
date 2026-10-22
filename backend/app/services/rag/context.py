from __future__ import annotations

from app.services.rag.retrieval import RetrievedTransaction

def format_retrieved_transactions(transactions: list[RetrievedTransaction]) -> str:
    if not transactions:
        return "No relevant transactions were found."

    sections = []

    for i, transaction in enumerate(transactions, start= 1):
        sections.append(f"[Transaction {i}]\n")