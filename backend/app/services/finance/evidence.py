from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FinanceEvidence:
    source_type: str
    data: Any
    description: str


def analytics_evidence(operation: str, data: Any) -> FinanceEvidence:
    
    return FinanceEvidence(
        source_type="analytics",
        data=data,
        description=f"Deterministic analytics result from {operation}.")


def rag_evidence(data: Any) -> FinanceEvidence:
    
    return FinanceEvidence(
        source_type="rag",
        data=data,
        description="Semantically retrieved transaction evidence.")