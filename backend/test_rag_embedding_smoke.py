import os
import pytest

from app.services.rag.embeddings import get_embedding_model


@pytest.mark.skipif(os.getenv("RUN_LIVE_AI_TESTS") != "1", reason="Live embedding smoke requires explicit opt-in")
def test_embedding_model_smoke():
    embeddings = get_embedding_model()

    vector = embeddings.embed_query(
        "How much did I spend on food?"
    )

    assert vector
    assert len(vector) > 0