"""Optional semantic retrieval exports, loaded only when explicitly used."""
from importlib import import_module

_EXPORTS = {
    "transaction_to_document": "documents",
    "transactions_to_documents": "documents",
    "get_embedding_model": "embeddings",
    "get_vector_store": "vector_store",
    "add_transaction_documents": "vector_store",
    "search_transactions": "vector_store",
    "RetrievedTransaction": "retrieval",
    "retrieve_transactions": "retrieval",
    "format_retrieved_transactions": "context",
    "FinanceAnswer": "qa",
    "answer_finance_question": "qa",
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(name)
    value = getattr(import_module(f"app.services.rag.{module}"), name)
    globals()[name] = value
    return value
