"""Optional chat factory, imported without loading vector or provider dependencies."""
from app.services.ai.provider import build_chat_model


def get_chat_model():
    return build_chat_model()
