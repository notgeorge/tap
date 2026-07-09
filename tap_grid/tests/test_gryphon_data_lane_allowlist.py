"""ROOT-1 — the data-lane field-path allowlist (`req-grid-traversal-lang-relation-guard.sec`).

Locks the confirmed cross-table read and its three sibling manifestations. Every post-`data`
token must resolve to a concrete declared field (a scalar column, or a key inside a declared
JSONField); anything else is rejected at the resolver, in WHERE and RETURN alike.

The seed finding was confirmed empirically on the live executor (the emitted SQL for
``MATCH (b:batch) WHERE b.data.actor.email = …`` carried ``INNER JOIN "tap_user"``, and
``RETURN b.data.actor.password`` projected the password hash). `Batch` is the reproduction
vehicle: it is a registered Gryphon type (``ENTITY_TYPE = "batch"``) with a ``ForeignKey`` to
the non-grid user table (``actor``), scalar columns (``name``/``source``), and a JSONField
(``metadata``).
"""

import pytest

from tap_grid.exceptions import SearchExecutionError
from tap_grid.gryphon import execute_gryphon_raw

pytestmark = pytest.mark.django_db(databases=["default", "search_readonly"])


class TestRelationCrossingRejected:
    """Manifestation 1 — the data lane may not cross a relation into another table."""

    def test_where_relation_walk_rejected(self):
        with pytest.raises(SearchExecutionError, match="relation"):
            execute_gryphon_raw(
                "MATCH (b:batch) WHERE b.data.actor.email = $e RETURN b",
                {"e": "x@example.com"},
            )

    def test_return_relation_walk_rejected(self):
        # The direct-exfiltration case: projecting the FK'd user table's password hash.
        with pytest.raises(SearchExecutionError, match="relation"):
            execute_gryphon_raw("MATCH (b:batch) RETURN b.data.actor.password", {})


class TestLookupTransformRejected:
    """Manifestation 2 — a Django lookup/transform token is not a declared field."""

    def test_transform_on_scalar_rejected(self):
        # `name` is a scalar column; `.regex` is a Django lookup, not a walkable sub-field.
        with pytest.raises(SearchExecutionError, match="scalar"):
            execute_gryphon_raw(
                "MATCH (b:batch) WHERE b.data.name.regex = $v RETURN b",
                {"v": "^x"},
            )


class TestUndeclaredFieldRejected:
    """Manifestation 3 — an undeclared field is a 422 rejection, not an uncaught 500."""

    def test_undeclared_field_rejected(self):
        with pytest.raises(SearchExecutionError, match="not a declared field"):
            execute_gryphon_raw(
                "MATCH (b:batch) WHERE b.data.nonesuch = $v RETURN b",
                {"v": "z"},
            )


class TestCompositeTokenSmugglingRejected:
    """Manifestation 4 — `__` / bracket-key cannot smuggle a multi-step walk in one token."""

    def test_double_underscore_dot_token_rejected(self):
        with pytest.raises(SearchExecutionError, match="__"):
            execute_gryphon_raw("MATCH (b:batch) RETURN b.data.actor__password", {})

    def test_bracket_key_smuggling_rejected(self):
        # Bracket keys are legal in WHERE; the embedded `__` is what's rejected.
        with pytest.raises(SearchExecutionError, match="__"):
            execute_gryphon_raw(
                'MATCH (b:batch) WHERE b.data["actor__password"] = $v RETURN b',
                {"v": "z"},
            )


class TestLegitimateDataLaneStillWorks:
    """Positive controls — the allowlist does not regress legitimate data-lane access."""

    def test_declared_scalar_projection_allowed(self):
        # The positive control is that a declared scalar projection resolves without the
        # allowlist rejection — reaching this assertion at all proves no error was raised.
        result = execute_gryphon_raw("MATCH (b:batch) RETURN b.data.name", {})
        assert isinstance(result, dict)

    def test_declared_scalar_where_allowed(self):
        result = execute_gryphon_raw(
            "MATCH (b:batch) WHERE b.data.source = $s RETURN b",
            {"s": "scanner:aws"},
        )
        assert "nodes" in result

    def test_json_field_key_walk_allowed(self):
        # `metadata` is a declared JSONField; walking into its keys is legitimate.
        result = execute_gryphon_raw(
            "MATCH (b:batch) WHERE b.data.metadata.run_id = $r RETURN b",
            {"r": "abc"},
        )
        assert "nodes" in result
