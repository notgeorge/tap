"""Tests for the search service layer — req-grid-search-exec + req-grid-search-readonly.sec."""

import pytest
from django.core.exceptions import ValidationError

from tap_grid.exceptions import SearchExecutionError
from tap_grid.models import Search
from tap_grid.search_service import (
    _normalize_envelope,
    _resolve_limit,
    _validate_inputs,
    execute_search,
)


def _orm_search(**kwargs):
    defaults = {
        "title": "Test",
        "search_type": "orm",
        "root": "node",
        "definition": {"filters": {"entity_type": "concept"}},
    }
    defaults.update(kwargs)
    return Search(**defaults)


def _module_search(**kwargs):
    defaults = {
        "title": "Module Test",
        "search_type": "module",
        "root": "node",
        "definition": {"runner_key": "tap_plugins.tests:example"},
    }
    defaults.update(kwargs)
    return Search(**defaults)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestValidateInputs:
    def test_no_schema_passes_any_inputs(self):
        s = _orm_search(input_schema=None)
        result = _validate_inputs(s, {"anything": True})
        assert result == {"anything": True}

    def test_empty_inputs_with_no_schema_pass(self):
        s = _orm_search(input_schema=None)
        assert _validate_inputs(s, {}) == {}

    def test_valid_inputs_pass_schema(self):
        schema = {
            "type": "object",
            "required": ["character_id"],
            "properties": {"character_id": {"type": "string"}},
        }
        s = _orm_search(input_schema=schema)
        result = _validate_inputs(s, {"character_id": "abc"})
        assert result == {"character_id": "abc"}

    def test_invalid_inputs_raise_validation_error(self):
        schema = {
            "type": "object",
            "required": ["character_id"],
            "properties": {"character_id": {"type": "string"}},
        }
        s = _orm_search(input_schema=schema)
        with pytest.raises(ValidationError) as exc_info:
            _validate_inputs(s, {})
        assert "inputs" in exc_info.value.message_dict

    def test_wrong_type_raises_validation_error(self):
        schema = {"type": "object", "properties": {"count": {"type": "integer"}}}
        s = _orm_search(input_schema=schema)
        with pytest.raises(ValidationError):
            _validate_inputs(s, {"count": "not-an-int"})


# ---------------------------------------------------------------------------
# Limit resolution
# ---------------------------------------------------------------------------


class TestResolveLimit:
    def test_no_caller_limit_no_default_returns_none(self):
        s = _orm_search(default_limit=None, max_limit=None)
        limit, warnings = _resolve_limit(s, None)
        assert limit is None
        assert warnings == {}

    def test_caller_limit_used_when_provided(self):
        s = _orm_search(default_limit=10, max_limit=None)
        limit, warnings = _resolve_limit(s, 25)
        assert limit == 25
        assert warnings == {}

    def test_default_limit_used_when_no_caller_limit(self):
        s = _orm_search(default_limit=20, max_limit=None)
        limit, warnings = _resolve_limit(s, None)
        assert limit == 20

    def test_clamped_to_max_limit(self):
        s = _orm_search(default_limit=None, max_limit=50)
        limit, warnings = _resolve_limit(s, 200)
        assert limit == 50
        assert "max_limit_clamped" in warnings
        assert warnings["max_limit_clamped"]["requested"] == 200
        assert warnings["max_limit_clamped"]["clamped_to"] == 50

    def test_within_max_limit_not_clamped(self):
        s = _orm_search(default_limit=None, max_limit=100)
        limit, warnings = _resolve_limit(s, 50)
        assert limit == 50
        assert warnings == {}

    def test_equal_to_max_limit_not_clamped(self):
        s = _orm_search(default_limit=None, max_limit=100)
        limit, warnings = _resolve_limit(s, 100)
        assert limit == 100
        assert warnings == {}


# ---------------------------------------------------------------------------
# Envelope normalization
# ---------------------------------------------------------------------------


class TestNormalizeEnvelope:
    def test_valid_envelope_passthrough(self):
        raw = {"nodes": [1, 2], "edges": [], "info": {"x": 1}, "warnings": {"w": True}}
        result = _normalize_envelope(raw)
        assert result["nodes"] == [1, 2]
        assert result["edges"] == []
        assert result["info"] == {"x": 1}
        assert result["warnings"] == {"w": True}

    def test_missing_nodes_raises(self):
        with pytest.raises(SearchExecutionError):
            _normalize_envelope({"edges": []})

    def test_missing_edges_raises(self):
        with pytest.raises(SearchExecutionError):
            _normalize_envelope({"nodes": []})

    def test_non_dict_raises(self):
        with pytest.raises(SearchExecutionError):
            _normalize_envelope(["not", "a", "dict"])

    def test_missing_info_defaults_to_empty_dict(self):
        result = _normalize_envelope({"nodes": [], "edges": []})
        assert result["info"] == {}

    def test_missing_warnings_defaults_to_empty_dict(self):
        result = _normalize_envelope({"nodes": [], "edges": []})
        assert result["warnings"] == {}


# ---------------------------------------------------------------------------
# execute_search dispatch
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestExecuteSearchDispatch:
    def test_unknown_search_type_raises_execution_error(self):
        """Unknown search_type raises SearchExecutionError (not AttributeError)."""
        # We bypass full_validate so we can test the service error path
        s = Search(
            search_type="sql",
            root="node",
            title="Bad",
            definition={"filters": {}},
        )
        with pytest.raises(SearchExecutionError, match="Unknown search_type"):
            execute_search(s)

    def test_orm_mode_raises_not_implemented_stub(self):
        """ORM execution stub raises SearchExecutionError until Phase 5."""
        s = Search.objects.create(
            search_type="orm",
            root="node",
            title="Stub Test",
            definition={"filters": {"entity_type": "concept"}},
        )
        with pytest.raises(SearchExecutionError, match="not yet implemented"):
            execute_search(s)

    def test_module_mode_raises_not_implemented_stub(self):
        """Module execution stub raises SearchExecutionError until Phase 4."""
        s = Search.objects.create(
            search_type="module",
            root="node",
            title="Module Stub",
            definition={"runner_key": "scope:key"},
        )
        with pytest.raises(SearchExecutionError, match="not yet implemented"):
            execute_search(s)

    def test_input_validation_fires_before_dispatch(self):
        """Input schema validation runs before the execution stub is reached."""
        s = Search.objects.create(
            search_type="orm",
            root="node",
            title="Validated",
            definition={"filters": {}},
            input_schema={"type": "object", "required": ["must_have"]},
        )
        with pytest.raises(ValidationError) as exc_info:
            execute_search(s, inputs={})
        assert "inputs" in exc_info.value.message_dict

    def test_max_limit_clamping_in_result(self):
        """Limit is clamped and warnings reflect the clamping (tested via stub path)."""
        s = Search.objects.create(
            search_type="orm",
            root="node",
            title="Limit Test",
            definition={"filters": {}},
            max_limit=10,
        )
        # The ORM stub raises before we get a result, so test _resolve_limit directly
        limit, warnings = _resolve_limit(s, 999)
        assert limit == 10
        assert "max_limit_clamped" in warnings


# ---------------------------------------------------------------------------
# Read-only DB alias
# ---------------------------------------------------------------------------


class TestReadOnlyDBAlias:
    def test_search_readonly_alias_exists_in_settings(self):
        from django.conf import settings

        assert "search_readonly" in settings.DATABASES

    def test_search_readonly_has_read_only_option(self):
        from django.conf import settings

        options = settings.DATABASES["search_readonly"].get("OPTIONS", {})
        pg_options = options.get("options", "")
        assert "default_transaction_read_only=on" in pg_options

    def test_search_readonly_points_to_same_host(self):
        from django.conf import settings

        default_host = settings.DATABASES["default"].get("HOST")
        readonly_host = settings.DATABASES["search_readonly"].get("HOST")
        assert default_host == readonly_host

    def test_search_readonly_points_to_same_user(self):
        from django.conf import settings

        default_user = settings.DATABASES["default"].get("USER")
        readonly_user = settings.DATABASES["search_readonly"].get("USER")
        assert default_user == readonly_user
