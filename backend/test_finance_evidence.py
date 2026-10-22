from app.services.finance.evidence import (analytics_evidence, rag_evidence)


def test_analytics_evidence():
    evidence = analytics_evidence(
        operation="category_spending",
        data={"Food": "5000.00"},
    )

    assert evidence.source_type == "analytics"
    assert evidence.data == {"Food": "5000.00"}
    assert "category_spending" in evidence.description


def test_rag_evidence():
    evidence = rag_evidence(
        data=["Foodpanda transaction"]
    )

    assert evidence.source_type == "rag"
    assert evidence.data == ["Foodpanda transaction"]