from __future__ import annotations

from app.services.finance.evidence import FinanceEvidence


def format_finance_evidence(
    evidence: list[FinanceEvidence],
) -> str:
    if not evidence:
        return ""

    sections = []

    for index, item in enumerate(evidence, start=1):
        sections.append(
            f"[Evidence {index}]\n"
            f"Source type: {item.source_type}\n"
            f"Description: {item.description}\n"
            f"Data:\n{item.data}"
        )

    return "\n\n".join(sections)