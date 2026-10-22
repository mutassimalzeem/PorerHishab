from app.services.rag.embeddings import get_embedding_model


def test_embedding_model_smoke():
    embeddings = get_embedding_model()

    vector = embeddings.embed_query(
        "How much did I spend on food?"
    )

    assert vector
    assert len(vector) > 0