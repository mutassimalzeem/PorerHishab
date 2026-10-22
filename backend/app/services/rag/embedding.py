from langchain_openai import OpenAIEmbeddings
from app.core.config import settings

def get_embedding_model() -> OpenAIEmbeddings:
    if not settings.OPENAI_KEY:
        raise RuntimeError("OpenAI_KEY is required for embedding")

    return OpenAIEmbeddings(model = settings.OPENAI_EMBEDDING_MODEL,
                            api_key= settings.OPENAI_KEY)
