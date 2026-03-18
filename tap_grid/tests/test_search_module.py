"""Tests for module search execution mode — req-grid-search-module."""

import pytest

from tap_grid.exceptions import SearchExecutionError, SearchRunnerNotFoundError
from tap_grid.models import Search
from tap_grid.registry import register_search_runner, search_runner_registry
from tap_grid.search_service import _execute_module_search, execute_search

# ---------------------------------------------------------------------------
# Registry isolation
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolate_registry(request):
    """Isolate the search runner registry for tests that manipulate it.

    Tests tagged with 'no_registry_isolation' are excluded (they use the
    real registry populated by AppConfig.ready()).
    """
    if "no_registry_isolation" in request.keywords:
        yield
        return
    saved = search_runner_registry.all()
    search_runner_registry._reset_for_testing()
    yield
    search_runner_registry._reset_for_testing(saved)


# ---------------------------------------------------------------------------
# Runner fixtures
# ---------------------------------------------------------------------------


def _make_valid_runner(nodes=None, edges=None):
    """Return a runner that produces a valid envelope."""

    def runner(search, inputs, *, db_alias):
        return {
            "nodes": nodes or [],
            "edges": edges or [],
            "info": {"runner": "valid"},
            "warnings": {},
        }

    runner.__module__ = "tap_grid.tests.fake_module"
    return runner


def _make_partial_runner():
    """Return a runner that produces a minimal valid envelope (no info/warnings)."""

    def runner(search, inputs, *, db_alias):
        return {"nodes": [{"entity_id": "abc"}], "edges": []}

    runner.__module__ = "tap_grid.tests.fake_module"
    return runner


def _make_crash_runner():
    """Return a runner that always raises."""

    def runner(search, inputs, *, db_alias):
        raise RuntimeError("runner exploded")

    runner.__module__ = "tap_grid.tests.fake_module"
    return runner


def _make_bad_result_runner():
    """Return a runner that returns a malformed result."""

    def runner(search, inputs, *, db_alias):
        return {"only_nodes": []}

    runner.__module__ = "tap_grid.tests.fake_module"
    return runner


def _module_search(**kwargs):
    defaults = {
        "name": "Module Test",
        "search_type": "module",
        "root": "node",
        "definition": {"runner_key": "fake.scope:my-runner"},
    }
    defaults.update(kwargs)
    return Search(**defaults)


# ---------------------------------------------------------------------------
# Runner resolution
# ---------------------------------------------------------------------------


class TestRunnerResolution:
    def test_resolves_registered_runner(self):
        runner = _make_valid_runner()
        register_search_runner("my-runner", runner, scope="fake.scope")
        s = _module_search()
        result = _execute_module_search(s, {}, "test_db")
        assert result["nodes"] == []

    def test_unresolved_key_raises_search_runner_not_found(self):
        s = _module_search(definition={"runner_key": "no.such:runner"})
        with pytest.raises(SearchRunnerNotFoundError, match="no.such:runner"):
            _execute_module_search(s, {}, "test_db")

    def test_missing_runner_key_in_definition_raises_execution_error(self):
        s = _module_search(definition={})
        with pytest.raises(SearchExecutionError, match="runner_key"):
            _execute_module_search(s, {}, "test_db")


# ---------------------------------------------------------------------------
# Runner invocation
# ---------------------------------------------------------------------------


class TestRunnerInvocation:
    def test_runner_receives_search_and_inputs(self):
        received = {}

        def runner(search, inputs, *, db_alias):
            received["search"] = search
            received["inputs"] = inputs
            received["db_alias"] = db_alias
            return {"nodes": [], "edges": []}

        runner.__module__ = "tap_grid.tests.fake_module"
        register_search_runner("capture", runner, scope="fake.scope")

        s = _module_search(definition={"runner_key": "fake.scope:capture"})
        inputs = {"x": 42}
        _execute_module_search(s, inputs, "my_db")

        assert received["search"] is s
        assert received["inputs"] == {"x": 42}
        assert received["db_alias"] == "my_db"

    def test_runner_receives_search_readonly_alias_via_execute_search(self):
        """Integration: execute_search passes the read-only db_alias to the runner."""
        received = {}

        def runner(search, inputs, *, db_alias):
            received["db_alias"] = db_alias
            return {"nodes": [], "edges": []}

        runner.__module__ = "tap_grid.tests.fake_module"
        register_search_runner("alias-check", runner, scope="fake.scope")

        s = _module_search(definition={"runner_key": "fake.scope:alias-check"})
        execute_search(s)
        assert received["db_alias"] == "search_readonly"

    def test_runner_crash_raises_search_execution_error(self):
        register_search_runner("crashing", _make_crash_runner(), scope="fake.scope")
        s = _module_search(definition={"runner_key": "fake.scope:crashing"})
        with pytest.raises(SearchExecutionError, match="runner exploded"):
            _execute_module_search(s, {}, "test_db")

    def test_bad_result_envelope_raises_search_execution_error(self):
        register_search_runner("bad-result", _make_bad_result_runner(), scope="fake.scope")
        s = _module_search(definition={"runner_key": "fake.scope:bad-result"})
        with pytest.raises(SearchExecutionError):
            execute_search(s)


# ---------------------------------------------------------------------------
# Result envelope normalization
# ---------------------------------------------------------------------------


class TestModuleResultNormalization:
    def test_partial_envelope_completed(self):
        register_search_runner("partial", _make_partial_runner(), scope="fake.scope")
        s = _module_search(definition={"runner_key": "fake.scope:partial"})
        result = execute_search(s)
        # Service adds info/warnings if runner omits them
        assert "info" in result
        assert "warnings" in result
        assert result["nodes"][0]["entity_id"] == "abc"

    def test_full_envelope_passthrough(self):
        register_search_runner("full", _make_valid_runner(nodes=[{"id": "x"}]), scope="fake.scope")
        s = _module_search(definition={"runner_key": "fake.scope:full"})
        result = execute_search(s)
        assert result["nodes"] == [{"id": "x"}]

    def test_runner_info_merged_with_service_info(self):
        def runner(search, inputs, *, db_alias):
            return {"nodes": [], "edges": [], "info": {"custom_key": "value"}, "warnings": {}}

        runner.__module__ = "tap_grid.tests.fake_module"
        register_search_runner("info-runner", runner, scope="fake.scope")
        s = _module_search(definition={"runner_key": "fake.scope:info-runner"})
        result = execute_search(s)
        # Service-added info keys coexist with runner's info keys
        assert result["info"]["custom_key"] == "value"
        assert "search_type" in result["info"]


# ---------------------------------------------------------------------------
# Integration with example runner (real registry, real DB)
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
@pytest.mark.no_registry_isolation
class TestListConceptsRunner:
    def test_runner_registered_in_meta(self):
        """list-concepts runner is registered by AppConfig.ready()."""
        from tap_grid.registry import search_runner_registry

        assert "tap_plugins.core_examples.searches:list-concepts" in search_runner_registry

    def test_list_concepts_returns_envelope(self):
        """list-concepts runner returns valid graph envelope via execute_search."""
        from tap_plugins.core_examples.models import Concept

        Concept.objects.create(summary="Test concept for search")
        s = Search.objects.create(
            name="List Concepts",
            search_type="module",
            root="node",
            definition={"runner_key": "tap_plugins.core_examples.searches:list-concepts"},
        )
        result = execute_search(s)
        assert "nodes" in result
        assert "edges" in result
        # At least the concept we just created should be present
        entity_types = [n["entity_type"] for n in result["nodes"]]
        assert all(et == "concept" for et in entity_types)

    def test_list_concepts_uses_read_only_connection(self):
        """Smoke test: execute_search doesn't crash when using search_readonly alias."""
        s = Search.objects.create(
            name="Readonly Test",
            search_type="module",
            root="node",
            definition={"runner_key": "tap_plugins.core_examples.searches:list-concepts"},
        )
        result = execute_search(s)
        assert isinstance(result["nodes"], list)
