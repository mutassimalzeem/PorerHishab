from __future__ import annotations

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.core.config import settings
from app.services.rag.embeddings import get_embedding_model

def get_vector_store() -> Chroma:
    return Chroma(
        collection_name=settings.VECTOR_COLLECTION_NAME,
        embedding_function=get_embedding_model(),
        persist_directory=settings.VECTOR_STORE_PATH)



def transaction_dict_to_document(transaction: dict) -> Document:
    return Document(
        page_content=transaction["page_content"],
        metadata=transaction["metadata"],
    )



def add_transaction_documents(transactions: list[dict]) -> list[str]:

    if not transactions:
        return []

    documents = [transaction_dict_to_document(transaction) for transaction in transactions]

    vector_store = get_vector_store()


    ids = [
        f"transaction-{transaction.metadata['transaction_id']}"
        for transaction in documents]

    vector_store.add_documents(documents=documents, ids=ids)
    
    return ids


def search_transactions(query: str, user_id: int, k: int = 5) -> list[Document]:
    vector_store = get_vector_store()

    results = vector_store.similarity_search(query, k = k, filter = {"user_id": user_id})   # filter -> security

    return results

