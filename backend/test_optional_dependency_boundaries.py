"""Optional package boundaries; SDK/store calls are explicit local doubles."""
import builtins
import importlib
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import BaseModel
from app.core.config import settings
from app.services.ai import provider
from app.services.rag import retrieval


def block_import(monkeypatch, module, failure):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name == module:
            raise failure
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)


def test_retrieval_import_does_not_load_optional_stack(monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.startswith(("langchain", "chromadb")) or name == "app.services.rag.vector_store":
            raise AssertionError("Import-only retrieval loaded optional adapter")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    importlib.reload(retrieval)


@pytest.mark.parametrize("missing", ["langchain_core", "langchain_chroma", "langchain_openai"])
def test_missing_rag_dependency_fails_closed_without_sensitive_payload(monkeypatch, caplog, missing):
    block_import(monkeypatch, "app.services.rag.vector_store",
                 ModuleNotFoundError("PRIVATE_PROVIDER_PAYLOAD", name=missing))
    with pytest.raises(RuntimeError, match="^Optional RAG dependencies are unavailable$") as error:
        retrieval.retrieve_transactions("query", 7)
    assert error.value.__suppress_context__
    assert "PRIVATE_PROVIDER_PAYLOAD" not in str(error.value)
    assert "PRIVATE_PROVIDER_PAYLOAD" not in caplog.text


@pytest.mark.parametrize("failure", [
    ModuleNotFoundError("internal adapter bug", name="app.missing_internal_module"),
    ImportError("incompatible installed SDK"),
])
def test_unexpected_import_failures_are_not_hidden(monkeypatch, failure):
    block_import(monkeypatch, "app.services.rag.vector_store", failure)
    with pytest.raises(type(failure)) as error:
        retrieval.retrieve_transactions("query", 7)
    assert error.value is failure


def test_loaded_adapter_receives_exact_scope_and_defense_still_filters(monkeypatch):
    adapter = ModuleType("app.services.rag.vector_store")
    search = Mock(return_value=[
        SimpleNamespace(page_content="mine", metadata={"user_id": 7}),
        SimpleNamespace(page_content="foreign", metadata={"user_id": 8}),
        SimpleNamespace(page_content="unscoped", metadata={}),
    ])
    adapter.search_transactions = search
    monkeypatch.setitem(sys.modules, adapter.__name__, adapter)
    result = retrieval.retrieve_transactions("  query  ", 7, 3)
    search.assert_called_once_with(query="query", user_id=7, k=3)
    assert [item.content for item in result] == ["mine"]


def test_missing_sdk_preserves_explicit_failure_and_optional_fallback(monkeypatch, caplog):
    class Output(BaseModel):
        value: str
    monkeypatch.setattr(settings, "AI_EXTERNAL_ENABLED", True)
    monkeypatch.setattr(settings, "OPENAI_KEY", "synthetic-key")
    failure = ModuleNotFoundError("PRIVATE_KEY_AND_PROVIDER_BODY", name="langchain_openai")
    block_import(monkeypatch, "langchain_openai", failure)
    with pytest.raises(ModuleNotFoundError) as error:
        provider.build_chat_model()
    assert error.value is failure
    assert provider.structured_optional(Output, "system", "payload") is None
    assert "PRIVATE_KEY_AND_PROVIDER_BODY" not in caplog.text


def test_missing_key_fails_before_any_sdk_import(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_KEY", None)
    block_import(monkeypatch, "langchain_openai", AssertionError("SDK import should not happen"))
    with pytest.raises(RuntimeError, match="not configured"):
        provider.build_chat_model()
