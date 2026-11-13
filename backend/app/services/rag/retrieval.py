from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_core.documents import Document


def search_transactions(query: str, user_id: int, k: int = 5):
    """Load the optional vector adapter only when retrieval is requested."""
    try:
        from app.services.rag.vector_store import search_transactions as search
    except ModuleNotFoundError as exc:
        # Missing optional roots are an availability error, never unscoped results.
        # Broken internal imports and incompatible installed modules must propagate.
        if exc.name not in {"langchain_core", "langchain_chroma", "langchain_openai"}:
            raise
        raise RuntimeError("Optional RAG dependencies are unavailable") from None
    return search(query=query, user_id=user_id, k=k)


@dataclass
class RetrievedTransaction:
    content: str
    metadata: dict[str, Any]


def retrieve_transactions(query: str, user_id: int, k: int = 5) -> list[RetrievedTransaction]:
    query = query.strip()

    if not query:
        raise ValueError("Query cannot be empty.")

    if user_id <= 0:
        raise ValueError("user_id must be positive.")

    if k <= 0:
        raise ValueError("k must be positive.")

    documents: list[Document] = search_transactions(
        query=query,
        user_id=user_id,
        k=k,
    )

    return [
        RetrievedTransaction(
            content=document.page_content,
            metadata=document.metadata,
        )
        for document in documents
        if document.metadata.get("user_id") == user_id
    ]
