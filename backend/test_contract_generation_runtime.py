"""Generator units use synthetic metadata/schema, not a claimed pinned runtime."""
from unittest.mock import Mock

import pytest
from app import main
from scripts import generate_frontend_contracts as contracts


def matching_versions(monkeypatch):
    pins = {}
    for line in (contracts.ROOT / "backend/requirements.txt").read_text().splitlines():
        name, separator, version = line.partition("==")
        if separator:
            pins[name] = version
    monkeypatch.setattr(contracts.metadata, "version", lambda name: pins[name])
    return pins


def test_exact_schema_toolchain_is_accepted(monkeypatch):
    matching_versions(monkeypatch)
    contracts.require_contract_runtime()


@pytest.mark.parametrize("package", contracts.SCHEMA_PACKAGES)
def test_mismatched_schema_package_blocks_generation_before_openapi(monkeypatch, package):
    pins = matching_versions(monkeypatch)
    monkeypatch.setattr(contracts.metadata, "version",
                        lambda name: "0.0.0" if name == package else pins[name])
    schema = Mock(side_effect=AssertionError("Schema must not be generated on the wrong runtime"))
    monkeypatch.setattr(main.app, "openapi", schema)
    with pytest.raises(contracts.ContractRuntimeMismatch, match=package):
        contracts.generate()
    schema.assert_not_called()


def test_absent_schema_package_is_reported(monkeypatch):
    matching_versions(monkeypatch)
    def missing(name):
        raise contracts.metadata.PackageNotFoundError(name)
    monkeypatch.setattr(contracts.metadata, "version", missing)
    with pytest.raises(contracts.ContractRuntimeMismatch, match="not installed"):
        contracts.require_contract_runtime()


def test_renderer_is_deterministic_and_preserves_schema_contract(monkeypatch):
    matching_versions(monkeypatch)
    spec = {
        "components": {"schemas": {
            "Example": {"type": "object", "required": ["id", "mode"], "properties": {
                "id": {"type": "integer"},
                "mode": {"enum": ["ready", "blocked"]},
                "note": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            }},
            "ValidationError": {"type": "object", "required": ["loc", "msg", "type"], "properties": {
                "loc": {"type": "array", "items": {"anyOf": [{"type": "string"}, {"type": "integer"}]}},
                "msg": {"type": "string"}, "type": {"type": "string"},
                "input": {}, "ctx": {"type": "object"},
            }},
            "HTTPValidationError": {"type": "object", "properties": {
                "detail": {"type": "array", "items": {"$ref": "#/components/schemas/ValidationError"}}
            }},
        }},
        "paths": {"/examples/{example_id}": {"post": {
            "parameters": [{"name": "limit", "in": "query", "schema": {"type": "integer"}, "required": False}],
            "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Example"}}}},
            "responses": {
                "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Example"}}}},
                "422": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/HTTPValidationError"}}}},
            },
        }}},
    }
    monkeypatch.setattr(main.app, "openapi", lambda: spec)
    first = contracts.generate()
    assert contracts.generate() == first
    assert '"id": number;' in first
    assert '"mode": "ready" | "blocked";' in first
    assert '"note"?: (string | null);' in first
    assert '"input"?: unknown;' in first and '"ctx"?: Record<string, unknown>;' in first
    assert '"detail"?: (ApiSchemas["ValidationError"])[];' in first
    assert '"POST /examples/{example_id}"' in first
    assert 'query: { "limit"?: number; };' in first
    assert 'body: ApiSchemas["Example"]; response: ApiSchemas["Example"];' in first


def test_schema_pins_match_required_versions(monkeypatch):
    assert {name: matching_versions(monkeypatch)[name] for name in contracts.SCHEMA_PACKAGES} == {
        "fastapi": "0.162.2", "starlette": "1.10.0",
        "pydantic": "2.14.1", "pydantic_core": "2.50.1",
    }


def test_mismatch_does_not_import_application(monkeypatch):
    import builtins
    monkeypatch.setattr(contracts.metadata, "version", lambda name: "0.0.0")
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "app.main":
            raise AssertionError("Application must not load before runtime validation")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    with pytest.raises(contracts.ContractRuntimeMismatch, match="schema runtime differs"):
        contracts.generate()


@pytest.mark.parametrize("package", contracts.SCHEMA_PACKAGES)
@pytest.mark.parametrize("argv", [[], ["--check"]])
def test_cli_mismatch_exits_without_overwriting_existing_output(monkeypatch, tmp_path, package, argv):
    requirements = (contracts.ROOT / "backend/requirements.txt").read_text(encoding="utf-8")
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend/requirements.txt").write_text(requirements, encoding="utf-8")
    target = tmp_path / "frontend/src/generated/api.ts"
    target.parent.mkdir(parents=True)
    original = b"// Existing contract must survive a runtime mismatch.\r\n"
    target.write_bytes(original)
    monkeypatch.setattr(contracts, "ROOT", tmp_path)
    pins = matching_versions(monkeypatch)
    monkeypatch.setattr(contracts.metadata, "version",
                        lambda name: "0.0.0" if name == package else pins[name])
    schema = Mock(side_effect=AssertionError("OpenAPI must not run on mismatch"))
    monkeypatch.setattr(main.app, "openapi", schema)

    with pytest.raises(SystemExit) as error:
        contracts.main(argv)

    assert isinstance(error.value.code, str)  # A diagnostic string gives CLI exit status 1.
    assert "Contract verification BLOCKED" in error.value.code
    assert f"{package}: expected {pins[package]}, found 0.0.0" in error.value.code
    assert "backend/requirements.txt" in error.value.code
    schema.assert_not_called()
    assert target.read_bytes() == original
