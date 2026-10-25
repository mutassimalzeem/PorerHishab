"""Shared optional OpenAI-compatible client with bounded work and no payload logging."""
from app.core.config import settings


def build_chat_model(config=None):
    config = config or settings
    if not config.OPENAI_KEY:
        raise RuntimeError("Optional AI provider is not configured")
    from langchain_openai import ChatOpenAI
    timeout = settings.AI_TIMEOUT_SECONDS
    tokens = settings.AI_MAX_OUTPUT_TOKENS
    options = dict(model=config.OPENAI_CHAT_MODEL, api_key=config.OPENAI_KEY,
                   temperature=0, timeout=max(1, min(float(timeout), 30)),
                   max_retries=0, max_tokens=max(64, min(int(tokens), 2000)))
    if config.OPENAI_BASE_URL:
        options["base_url"] = config.OPENAI_BASE_URL
    return ChatOpenAI(**options)


def structured_optional(schema, system, payload):
    if not settings.AI_EXTERNAL_ENABLED or not settings.OPENAI_KEY:
        return None
    if len(system) > 6000 or len(payload) > 12000:
        return None
    try:
        result = build_chat_model().with_structured_output(schema).invoke([
            ("system", system), ("human", payload),
        ])
        return schema.model_validate(result.model_dump() if hasattr(result, "model_dump") else result)
    except Exception:
        # Provider errors can contain prompts, URLs or secrets; never return/log them.
        return None
