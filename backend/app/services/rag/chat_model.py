from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.core.config import settings


def get_chat_model() -> ChatOpenAI:
    if not settings.OPENAI_KEY:
        raise RuntimeError("OPENAI_KEY is required for chat.")

    return ChatOpenAI(
        model=settings.OPENAI_CHAT_MODEL,
        api_key=settings.OPENAI_KEY,
        base_url=settings.OPENAI_BASE_URL,
        temperature=0,
    )