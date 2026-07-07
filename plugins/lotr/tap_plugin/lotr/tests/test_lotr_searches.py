"""Integration coverage for the LOTR-supplied module-search runner.

The generic module-search MECHANISM (registration, invocation, envelope
normalization) is tested with synthetic runners in
tap_grid/tests/test_search_module.py. This suite is the concrete
plugin-runner check: it lives with the plugin that ships the runner, and
verifies lotr's ``list-characters-with-bio`` registers via AppConfig.ready()
and executes end-to-end through execute_search.
"""

import pytest

# Import models to trigger constraint/type registration via __init_subclass__.
import tap_plugin.lotr.models  # noqa: F401

from tap_grid.models import Search
from tap_grid.search import execute_search


@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
@pytest.mark.no_registry_isolation
class TestListCharactersRunner:
    def test_runner_registered_in_meta(self):
        """list-characters-with-bio runner is registered by AppConfig.ready()."""
        from tap_grid.registry import search_runner_registry

        assert "tap_plugin.lotr.searches.characters:list-characters-with-bio" in search_runner_registry

    def test_list_characters_returns_envelope(self):
        """list-characters-with-bio runner returns a valid graph envelope via execute_search."""
        from tap_plugin.lotr.models import Character

        Character.objects.create(bio="Test character for search")
        s = Search.objects.create(
            name="List Characters",
            search_type="module",
            root="node",
            definition={"runner_key": "tap_plugin.lotr.searches.characters:list-characters-with-bio"},
        )
        result = execute_search(s)
        assert "nodes" in result
        assert "edges" in result
        # At least the character we just created should be present.
        entity_types = [n["entity_type"] for n in result["nodes"]]
        assert all(et == "lotr__character" for et in entity_types)

    def test_list_characters_uses_read_only_connection(self):
        """Smoke test: execute_search doesn't crash when using the search_readonly alias."""
        s = Search.objects.create(
            name="Readonly Test",
            search_type="module",
            root="node",
            definition={"runner_key": "tap_plugin.lotr.searches.characters:list-characters-with-bio"},
        )
        result = execute_search(s)
        assert isinstance(result["nodes"], list)
