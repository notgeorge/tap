"""Tests for the Gryphon SQL capture seam — ``tap_grid/gryphon/capture.py``.

These verify the capture *mechanism*: that ``capture_sql()`` /
``explain_gryphon_raw()`` record the SELECT statements a Gryphon run issues,
in order, stage-labelled, and deterministically. They assert the seam, not
executor correctness — executor correctness is Gridkin's job
(``plugins/gryphon_playground/``).

Seeding uses direct ORM writes (an intentional below-service-layer test);
the executor reads the same ``default`` alias the data is seeded on.
"""

import pytest

from tap_grid.gryphon import capture_sql, execute_gryphon_raw, explain_gryphon_raw
from tap_grid.gryphon.capture import SqlCapture

# Undirected one-hop with a WHERE anchor → hub-and-spoke dispatch.
_HUB_SPOKE = "MATCH (a)-[e]-(b) WHERE a.entity_id = $id RETURN a, e, b"


def _seed_hub_graph():
    """Seed a hub character with three location neighbors via LOCATED_IN.

    Returns the hub Entity. The three-neighbor fan-out gives the executor a
    ``pk__in`` over a set of three ids — the statement whose ordering the
    determinism fix pins down.
    """
    from tap_grid.models import Edge, Entity

    hub = Entity.objects.create(entity_type="character", name="Hub")
    for index in range(3):
        neighbor = Entity.objects.create(entity_type="location", name=f"Neighbor {index}")
        Edge.objects.create(
            entity=Entity.objects.create(entity_type="edge"),
            from_entity=hub,
            to_entity=neighbor,
            edge_type="LOCATED_IN",
        )
    return hub


@pytest.mark.django_db(transaction=True, databases=["default", "search_readonly"])
class TestGryphonSqlCapture:
    """The capture seam records, labels, and renders the executor's SQL."""

    def test_explain_returns_envelope_and_capture(self):
        hub = _seed_hub_graph()
        result = explain_gryphon_raw(_HUB_SPOKE, {"id": str(hub.pk)}, layer="lite")
        assert set(result) == {"envelope", "sql"}
        assert isinstance(result["sql"], SqlCapture)
        assert "nodes" in result["envelope"] and "edges" in result["envelope"]

    def test_explain_envelope_matches_plain_execute(self):
        hub = _seed_hub_graph()
        inputs = {"id": str(hub.pk)}
        explained = explain_gryphon_raw(_HUB_SPOKE, inputs, layer="lite")
        executed = execute_gryphon_raw(_HUB_SPOKE, inputs, layer="lite")
        assert explained["envelope"] == executed

    def test_capture_records_only_reads(self):
        hub = _seed_hub_graph()
        result = explain_gryphon_raw(_HUB_SPOKE, {"id": str(hub.pk)}, layer="lite")
        statements = result["sql"].statements
        # Hub load + outbound edge scan + inbound edge scan + neighbor fetch.
        assert len(statements) >= 2
        for stmt in statements:
            assert stmt.sql.lstrip().upper().startswith(("SELECT", "WITH"))

    def test_capture_is_stage_labelled_hub_and_spoke(self):
        hub = _seed_hub_graph()
        result = explain_gryphon_raw(_HUB_SPOKE, {"id": str(hub.pk)}, layer="lite")
        assert {s.stage for s in result["sql"].statements} == {"hub-and-spoke"}

    def test_edge_type_scan_stage_label(self):
        _seed_hub_graph()
        query = "MATCH (c:character)-[e:LOCATED_IN]->(l:location)"
        result = explain_gryphon_raw(query, {}, layer="lite")
        assert result["sql"].statements
        assert {s.stage for s in result["sql"].statements} == {"edge-type-scan"}

    def test_advanced_stage_label(self):
        _seed_hub_graph()
        query = "MATCH (c:character)-[:LOCATED_IN]->(l:location) " "RETURN c.entity_id AS cid, COUNT(l) AS n"
        result = explain_gryphon_raw(query, {}, layer="lite")
        assert result["sql"].statements
        assert {s.stage for s in result["sql"].statements} == {"advanced"}

    def test_in_list_params_are_sorted(self):
        """The neighbor-fetch filters ``pk__in`` over a Python set; the executor
        sorts it so the emitted ``IN (...)`` list is deterministic across
        processes (set iteration order is hash-randomized per process)."""
        hub = _seed_hub_graph()
        result = explain_gryphon_raw(_HUB_SPOKE, {"id": str(hub.pk)}, layer="lite")
        in_statements = [s for s in result["sql"].statements if " IN (" in s.sql]
        assert in_statements, "expected an IN-list statement over the 3 neighbor ids"
        for stmt in in_statements:
            params = [str(p) for p in stmt.params]
            assert params == sorted(params), f"IN-list params not sorted: {params}"

    def test_capture_is_deterministic(self):
        hub = _seed_hub_graph()
        inputs = {"id": str(hub.pk)}
        first = explain_gryphon_raw(_HUB_SPOKE, inputs, layer="lite")["sql"].render()
        second = explain_gryphon_raw(_HUB_SPOKE, inputs, layer="lite")["sql"].render()
        assert first == second

    def test_render_is_multi_statement(self):
        hub = _seed_hub_graph()
        rendered = explain_gryphon_raw(_HUB_SPOKE, {"id": str(hub.pk)}, layer="lite")["sql"].render()
        assert "-- statement 1 · stage: hub-and-spoke" in rendered
        assert "-- statement 2" in rendered

    def test_capture_inactive_without_block(self):
        # Executing outside a capture_sql() block must work and record nothing.
        hub = _seed_hub_graph()
        execute_gryphon_raw(_HUB_SPOKE, {"id": str(hub.pk)}, layer="lite")
        with capture_sql() as cap:
            pass
        assert cap.statements == []
